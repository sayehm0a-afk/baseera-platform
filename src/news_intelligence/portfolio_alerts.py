"""portfolio_alerts.py: PortfolioNewsAlertEngine -- re-evaluates a
portfolio's held positions whenever critical news arrives and
generates Upgrade/Downgrade/High Risk/Major Opportunity alerts.

Classification is a deliberately simple, disclosed rule over each
held symbol's most recent *canonical, analyzed* news events (never a
duplicate/syndicated copy, and never an unanalyzed "collected but no
LLM result" row) -- category and sentiment/confidence thresholds, not
a second scoring engine. Every alert is persisted twice: once as a
structured, queryable `PortfolioNewsAlert` row (the durable record of
what was flagged, matching `MarketAlert`'s own "generation only, no
notification delivery mechanism" scope), and once as a
`Notification(type=PORTFOLIO_ALERT)` row for the portfolio's owner --
reusing the existing per-user notification feed rather than building a
second delivery mechanism. Idempotent: an alert is never generated
twice for the same (portfolio, news_event) pair.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.domain.models import (
    AlertSeverity,
    NewsCategory,
    NewsEntity,
    NewsEntityType,
    NewsEvent,
    Notification,
    NotificationType,
    Portfolio,
    PortfolioAlertType,
    PortfolioNewsAlert,
)
from src.news_intelligence.config import (
    get_alert_high_risk_sentiment_threshold,
    get_alert_major_opportunity_threshold,
    get_alert_min_confidence,
)
from src.news_intelligence.types import PortfolioAlert

_HIGH_RISK_CATEGORIES = {
    NewsCategory.LAWSUIT, NewsCategory.BANKRUPTCY, NewsCategory.TRADING_SUSPENSION, NewsCategory.REGULATORY_CHANGE,
}

_SEVERITY_BY_ALERT_TYPE = {
    PortfolioAlertType.HIGH_RISK: AlertSeverity.CRITICAL,
    PortfolioAlertType.DOWNGRADE: AlertSeverity.WARNING,
    PortfolioAlertType.MAJOR_OPPORTUNITY: AlertSeverity.WARNING,
    PortfolioAlertType.UPGRADE: AlertSeverity.INFO,
}


def classify_alert_type(category: NewsCategory, sentiment_score: float, confidence: float) -> Optional[PortfolioAlertType]:
    """Pure classification rule, no I/O -- returns `None` when the
    event does not clear the minimum-confidence bar or isn't
    directionally clear enough to act on."""
    if confidence < get_alert_min_confidence():
        return None
    if category in _HIGH_RISK_CATEGORIES or sentiment_score <= get_alert_high_risk_sentiment_threshold():
        return PortfolioAlertType.HIGH_RISK
    if sentiment_score >= get_alert_major_opportunity_threshold():
        return PortfolioAlertType.MAJOR_OPPORTUNITY
    if sentiment_score >= 0.2:
        return PortfolioAlertType.UPGRADE
    if sentiment_score <= -0.2:
        return PortfolioAlertType.DOWNGRADE
    return None


def build_alert_message(symbol: str, alert_type: PortfolioAlertType, event: NewsEvent) -> str:
    label = {
        PortfolioAlertType.HIGH_RISK: "High risk",
        PortfolioAlertType.DOWNGRADE: "Downgrade signal",
        PortfolioAlertType.MAJOR_OPPORTUNITY: "Major opportunity",
        PortfolioAlertType.UPGRADE: "Upgrade signal",
    }[alert_type]
    return f"{label} for {symbol}: {event.headline} ({event.category.value if event.category else 'OTHER'})."


# Pre-launch safety fix (2026-08-22, Priority 2): Arabic label
# companions for the enums this module already classifies by -- kept in
# lockstep with frontend/src/lib/news-labels.ts's NEWS_CATEGORY_LABELS/
# PORTFOLIO_ALERT_TYPE_LABELS so both surfaces show the same wording.
# Presentation only: does not change classify_alert_type's rule or any
# stored English `message`/title -- only adds an Arabic companion.
_ALERT_TYPE_LABELS_AR = {
    PortfolioAlertType.HIGH_RISK: "مخاطرة عالية",
    PortfolioAlertType.DOWNGRADE: "إشارة تخفيض",
    PortfolioAlertType.MAJOR_OPPORTUNITY: "فرصة كبرى",
    PortfolioAlertType.UPGRADE: "إشارة ترقية",
}

_NEWS_CATEGORY_LABELS_AR = {
    NewsCategory.EARNINGS: "أرباح",
    NewsCategory.DIVIDEND: "توزيعات أرباح",
    NewsCategory.CONTRACT_AWARD: "ترسية عقد",
    NewsCategory.EXPANSION: "توسع",
    NewsCategory.ACQUISITION: "استحواذ",
    NewsCategory.LAWSUIT: "قضية قانونية",
    NewsCategory.REGULATORY_CHANGE: "تغيير تنظيمي",
    NewsCategory.GOVERNMENT_POLICY: "سياسة حكومية",
    NewsCategory.OIL: "النفط",
    NewsCategory.INTEREST_RATES: "أسعار الفائدة",
    NewsCategory.INFLATION: "التضخم",
    NewsCategory.CURRENCY: "العملة",
    NewsCategory.SUPPLY_CHAIN: "سلسلة الإمداد",
    NewsCategory.PRODUCTION: "الإنتاج",
    NewsCategory.GUIDANCE: "توجيهات الشركة",
    NewsCategory.CREDIT_RATING: "التصنيف الائتماني",
    NewsCategory.EXECUTIVE_CHANGE: "تغيير تنفيذي",
    NewsCategory.BANKRUPTCY: "إفلاس",
    NewsCategory.TRADING_SUSPENSION: "إيقاف تداول",
    NewsCategory.OTHER: "أخرى",
}


def build_alert_message_ar(symbol: str, alert_type: PortfolioAlertType, event: NewsEvent) -> str:
    """Arabic companion to `build_alert_message` -- same structure and
    same underlying data (symbol, alert type, category), fully Arabic
    except the news headline itself, which is real article text in
    whatever language it was published and is not translated here (no
    LLM call is introduced by this presentation fix)."""
    label_ar = _ALERT_TYPE_LABELS_AR[alert_type]
    category_ar = _NEWS_CATEGORY_LABELS_AR[event.category] if event.category else _NEWS_CATEGORY_LABELS_AR[NewsCategory.OTHER]
    return f"{label_ar} لسهم {symbol}: {event.headline} ({category_ar})."


class PortfolioNewsAlertEngine:
    def generate_and_persist(
        self, session: Session, portfolio: Portfolio, symbols: List[str], since: Optional[datetime] = None
    ) -> List[PortfolioAlert]:
        """Scans each held `symbols` entry for canonical, analyzed news
        events published since `since` (defaults to "no lower bound" --
        the caller, e.g. a scheduled job, is expected to pass its own
        last-run timestamp to avoid re-scanning full history every
        time), classifies each, and persists any that clear the bar --
        skipping any (portfolio, news_event) pair already alerted on.
        """
        alerts: List[PortfolioAlert] = []
        for symbol in symbols:
            query = (
                session.query(NewsEvent)
                .join(NewsEntity, NewsEntity.news_event_id == NewsEvent.id)
                .filter(
                    NewsEntity.entity_type == NewsEntityType.COMPANY,
                    NewsEntity.symbol == symbol,
                    NewsEvent.duplicate_of_id.is_(None),
                    NewsEvent.analyzed_at.isnot(None),
                )
            )
            if since is not None:
                query = query.filter(NewsEvent.published_at >= since)

            for event in query.all():
                alert_type = classify_alert_type(
                    event.category or NewsCategory.OTHER, event.sentiment_score or 0.0, event.confidence or 0.0
                )
                if alert_type is None:
                    continue

                already_alerted = (
                    session.query(PortfolioNewsAlert.id)
                    .filter_by(portfolio_id=portfolio.id, news_event_id=event.id)
                    .first()
                )
                if already_alerted is not None:
                    continue

                severity = _SEVERITY_BY_ALERT_TYPE[alert_type]
                message = build_alert_message(symbol, alert_type, event)
                message_ar = build_alert_message_ar(symbol, alert_type, event)
                generated_at = datetime.now(timezone.utc)

                alert_row = PortfolioNewsAlert(
                    portfolio_id=portfolio.id, symbol=symbol, news_event_id=event.id, alert_type=alert_type,
                    severity=severity, message=message, message_ar=message_ar, generated_at=generated_at,
                )
                session.add(alert_row)
                session.flush()  # populates alert_row.id before it's threaded into the returned dataclass
                if portfolio.user_id is not None:
                    session.add(
                        Notification(
                            user_id=portfolio.user_id, type=NotificationType.PORTFOLIO_ALERT,
                            title=f"{symbol}: {alert_type.value.replace('_', ' ').title()}", body=message,
                            title_ar=f"{_ALERT_TYPE_LABELS_AR[alert_type]}: {symbol}", body_ar=message_ar,
                        )
                    )
                alerts.append(
                    PortfolioAlert(
                        id=alert_row.id, portfolio_id=portfolio.id, symbol=symbol, news_event_id=event.id,
                        alert_type=alert_type, severity=severity, message=message, message_ar=message_ar,
                        generated_at=generated_at,
                    )
                )

        if alerts:
            session.commit()
        return alerts
