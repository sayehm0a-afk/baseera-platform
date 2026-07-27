"""DataExportService: builds the structured "download my data" export
for GET /api/v1/auth/me/export (Phase 13 P13.6). Read-only, always
scoped to the calling `User` row (never accepts a foreign user id) --
see src/api/routes/auth.py for the ownership guarantee (the route only
ever passes `current_user`, resolved from the caller's own session).

Deliberately excludes: `password_hash`, every session's
`refresh_token_jti`/`family_id` (token material -- even though
`refresh_token_jti` is itself a one-way hash, not the raw token, it is
still internal security material with no reason to leave the system),
`EmailVerificationToken`/`PasswordResetToken` rows (token hashes, no
customer-facing value), `AuditLog`/`AIRequest.estimated_cost_usd`-style
internal telemetry not about this specific user's own product usage,
and any other user's data (every query below filters by `user.id`,
never a caller-supplied id).

Audit trail: logged via structured application logging, same reasoning
as `user_service.delete_own_account`'s docstring -- this is a
self-service action, not an admin one, so it doesn't belong in the
staff-scoped `AuditLog` table.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from src.domain.models import (
    Feedback,
    Invoice,
    Notification,
    Payment,
    Portfolio,
    PortfolioNewsAlert,
    RecommendationHistory,
    Report,
    Subscription,
    SupportTicket,
    User,
    UserSession,
    UserSetting,
    UserWatchlist,
)


logger = logging.getLogger(__name__)


def _iso(value):
    return value.isoformat() if value is not None else None


def build_user_data_export(session: Session, user: User) -> Dict[str, Any]:
    """Returns a fully JSON-serializable dict -- every value is already
    a str/int/float/bool/None/list/dict, so callers can hand this
    straight to a JSON response with no further conversion. Order of
    dict construction is deterministic (fixed field order, DB-level
    `.order_by()` on every list) so two calls against the same
    unmodified data always produce byte-identical output."""
    logger.info("Self-service data export requested.", extra={"extra_fields": {"user_id": user.id}})

    export: Dict[str, Any] = {
        "profile": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_email_verified": user.is_email_verified,
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
        },
        "subscription": None,
        "sessions": [],
        "portfolios": [],
        "watchlists": [],
        "settings": None,
        "notifications": [],
        "invoices": [],
        "feedback": [],
        "support_tickets": [],
        "recommendation_history": [],
        "reports": [],
    }

    subscription = session.query(Subscription).filter_by(user_id=user.id).one_or_none()
    if subscription is not None:
        export["subscription"] = {
            "plan": subscription.plan.value,
            "status": subscription.status.value,
            "trial_ends_at": _iso(subscription.trial_ends_at),
            "current_period_start": _iso(subscription.current_period_start),
            "current_period_end": _iso(subscription.current_period_end),
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    sessions = (
        session.query(UserSession).filter_by(user_id=user.id).order_by(UserSession.issued_at.desc()).all()
    )
    export["sessions"] = [
        {
            "device_label": s.device_label,
            "ip_address": s.ip_address,
            "issued_at": _iso(s.issued_at),
            "last_used_at": _iso(s.last_used_at),
            "expires_at": _iso(s.expires_at),
            "revoked_at": _iso(s.revoked_at),
        }
        for s in sessions
    ]

    portfolios = session.query(Portfolio).filter_by(user_id=user.id).order_by(Portfolio.id).all()
    portfolio_export = []
    for p in portfolios:
        holdings = sorted(p.holdings, key=lambda h: h.symbol)
        alerts = (
            session.query(PortfolioNewsAlert)
            .filter_by(portfolio_id=p.id)
            .order_by(PortfolioNewsAlert.generated_at.desc())
            .all()
        )
        portfolio_export.append(
            {
                "name": p.name,
                "cash_balance": float(p.cash_balance),
                "created_at": _iso(p.created_at),
                "updated_at": _iso(p.updated_at),
                "holdings": [
                    {
                        "symbol": h.symbol,
                        "quantity": float(h.quantity),
                        "average_cost": float(h.average_cost) if h.average_cost is not None else None,
                        "created_at": _iso(h.created_at),
                    }
                    for h in holdings
                ],
                "news_alerts": [
                    {
                        "symbol": a.symbol,
                        "alert_type": a.alert_type.value,
                        "severity": a.severity.value,
                        "message": a.message,
                        "generated_at": _iso(a.generated_at),
                        "acknowledged_at": _iso(a.acknowledged_at),
                    }
                    for a in alerts
                ],
            }
        )
    export["portfolios"] = portfolio_export

    watchlists = session.query(UserWatchlist).filter_by(user_id=user.id).order_by(UserWatchlist.id).all()
    export["watchlists"] = [
        {
            "name": w.name,
            "created_at": _iso(w.created_at),
            "items": [
                {"symbol": i.symbol, "added_at": _iso(i.added_at)}
                for i in sorted(w.items, key=lambda i: i.symbol)
            ],
        }
        for w in watchlists
    ]

    settings = session.query(UserSetting).filter_by(user_id=user.id).one_or_none()
    if settings is not None:
        export["settings"] = settings.preferences_json

    notifications = (
        session.query(Notification).filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
    )
    export["notifications"] = [
        {
            "type": n.type.value,
            "title": n.title,
            "body": n.body,
            "read_at": _iso(n.read_at),
            "created_at": _iso(n.created_at),
        }
        for n in notifications
    ]

    invoices = session.query(Invoice).filter_by(user_id=user.id).order_by(Invoice.issued_at.desc()).all()
    invoice_export = []
    for inv in invoices:
        payments = session.query(Payment).filter_by(invoice_id=inv.id).order_by(Payment.created_at).all()
        invoice_export.append(
            {
                "amount": float(inv.amount),
                "currency": inv.currency,
                "status": inv.status.value,
                "issued_at": _iso(inv.issued_at),
                "paid_at": _iso(inv.paid_at),
                "payments": [
                    {"amount": float(pay.amount), "status": pay.status.value, "created_at": _iso(pay.created_at)}
                    for pay in payments
                ],
            }
        )
    export["invoices"] = invoice_export

    feedback_rows = session.query(Feedback).filter_by(user_id=user.id).order_by(Feedback.created_at.desc()).all()
    export["feedback"] = [
        {
            "category": f.category.value,
            "message": f.message,
            "page_context": f.page_context,
            "created_at": _iso(f.created_at),
        }
        for f in feedback_rows
    ]

    tickets = session.query(SupportTicket).filter_by(user_id=user.id).order_by(SupportTicket.created_at.desc()).all()
    export["support_tickets"] = [
        {
            "subject": t.subject,
            "message": t.message,
            "status": t.status.value,
            "created_at": _iso(t.created_at),
            "resolved_at": _iso(t.resolved_at),
        }
        for t in tickets
    ]

    history = (
        session.query(RecommendationHistory)
        .filter_by(user_id=user.id)
        .order_by(RecommendationHistory.viewed_at.desc())
        .all()
    )
    export["recommendation_history"] = [
        {
            "symbol": h.symbol,
            "recommendation": h.recommendation,
            "confidence": h.confidence,
            "source": h.source,
            "viewed_at": _iso(h.viewed_at),
        }
        for h in history
    ]

    reports = session.query(Report).filter_by(user_id=user.id).order_by(Report.requested_at.desc()).all()
    export["reports"] = [
        {
            "report_type": r.report_type.value,
            "title": r.title,
            "status": r.status.value,
            "file_url": r.file_url,
            "requested_at": _iso(r.requested_at),
            "generated_at": _iso(r.generated_at),
        }
        for r in reports
    ]

    # AIRequest rows are deliberately not included -- they're aggregate
    # cost/usage accounting for the platform's own operational reporting
    # (src/api/routes/admin/usage.py), not a customer-facing product
    # feature; `user_id` on them exists only for admin-side attribution
    # and is already excluded from every admin response schema too.

    logger.info("Self-service data export completed.", extra={"extra_fields": {"user_id": user.id}})
    return export
