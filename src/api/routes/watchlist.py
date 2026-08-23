"""GET/POST/DELETE /api/v1/watchlist -- the authenticated user's own
personal watchlist. Every route resolves the target watchlist strictly
from `current_user.id` (never from a client-supplied watchlist/item
id), so there is no parameter through which one user could ever name
another user's watchlist -- the strongest defense against IDOR is not
exposing the foreign key at all.

Each user has exactly one watchlist, created lazily on first read or
first add (`UserWatchlist.name` is a fixed, non-user-facing label --
this route does not expose Basirah's underlying multi-watchlist-per-
user schema as a product feature, since nothing has asked for named
watchlists yet).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.analysis.decision_v2.decision_freshness import classify_decision_freshness, is_decision_fresh
from src.api.dependencies import get_current_user
from src.api.exceptions import StockNotFoundError, WatchlistItemAlreadyExistsError, WatchlistItemNotFoundError
from src.api.schemas.auth import MessageOut
from src.api.schemas.watchlist import (
    AddWatchlistItemRequest,
    WatchlistItemOut,
    WatchlistNewsAlertListOut,
    WatchlistNewsAlertOut,
    WatchlistOut,
)
from src.core.db.database import get_db
from src.domain.models import (
    DecisionV2Snapshot,
    RadarOpportunity,
    Stock,
    User,
    UserWatchlist,
    UserWatchlistItem,
    WatchlistNewsAlert,
)
from src.market_data.validators.symbol_validator import InvalidSymbolError, validate_symbol_format
from src.market_intelligence.market_status import get_market_status
from src.market_intelligence.radar_v2 import current_live_opportunity
from src.news_intelligence.watchlist_alerts import WatchlistNewsAlertEngine

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

_DEFAULT_WATCHLIST_NAME = "المحفظة الافتراضية"


def _get_or_create_watchlist(session: Session, user_id: int) -> UserWatchlist:
    watchlist = session.query(UserWatchlist).filter_by(user_id=user_id).order_by(UserWatchlist.id).first()
    if watchlist is not None:
        return watchlist
    watchlist = UserWatchlist(user_id=user_id, name=_DEFAULT_WATCHLIST_NAME)
    session.add(watchlist)
    session.commit()
    return watchlist


def _item_out(
    item: UserWatchlistItem,
    stock: Stock,
    latest: DecisionV2Snapshot | None,
    radar: RadarOpportunity | None,
    market_status=None,
) -> WatchlistItemOut:
    return WatchlistItemOut(
        symbol=item.symbol,
        added_at=item.added_at,
        company_name_ar=stock.name_ar,
        sector_ar=stock.sector,
        latest_decision=latest.decision if latest else None,
        latest_decision_label_ar=latest.decision_label_ar if latest else None,
        latest_confidence_score=float(latest.confidence_score) if latest else None,
        latest_current_price=float(latest.current_price) if latest and latest.current_price is not None else None,
        latest_entry_zone_low=(
            float(latest.entry_zone_low) if latest and latest.entry_zone_low is not None else None
        ),
        latest_entry_zone_high=(
            float(latest.entry_zone_high) if latest and latest.entry_zone_high is not None else None
        ),
        latest_target_1=float(latest.target_1) if latest and latest.target_1 is not None else None,
        latest_target_2=float(latest.target_2) if latest and latest.target_2 is not None else None,
        latest_target_3=float(latest.target_3) if latest and latest.target_3 is not None else None,
        latest_stop_loss=float(latest.stop_loss) if latest and latest.stop_loss is not None else None,
        latest_data_freshness_status=latest.data_freshness_status if latest else None,
        latest_decision_timestamp=latest.decision_timestamp if latest else None,
        latest_decision_freshness_status=(
            classify_decision_freshness(latest.decision_timestamp, market_status).value if latest else None
        ),
        latest_is_decision_fresh=(
            is_decision_fresh(latest.decision_timestamp, market_status) if latest else None
        ),
        radar_is_live_opportunity=radar is not None,
        radar_stage1_rank=radar.stage1_rank if radar else None,
        radar_ranking_reason_ar=radar.ranking_reason_ar if radar else None,
    )


@router.get("", response_model=WatchlistOut)
def get_watchlist(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistOut:
    watchlist = _get_or_create_watchlist(session, current_user.id)
    items = (
        session.query(UserWatchlistItem)
        .filter(UserWatchlistItem.watchlist_id == watchlist.id)
        .order_by(UserWatchlistItem.added_at.desc())
        .all()
    )

    # Computed once per request (a pure function of wall-clock time, not
    # per-item) so every item's freshness verdict is judged against the
    # exact same session boundary.
    market_status = get_market_status()

    out_items = []
    for item in items:
        stock = session.query(Stock).filter(Stock.id == item.stock_id).first()
        latest = (
            session.query(DecisionV2Snapshot)
            .filter(DecisionV2Snapshot.symbol == item.symbol)
            .order_by(DecisionV2Snapshot.decision_timestamp.desc())
            .first()
        )
        radar = current_live_opportunity(session, item.symbol)
        out_items.append(_item_out(item, stock, latest, radar, market_status))

    return WatchlistOut(generated_at=datetime.now(timezone.utc), items=out_items)


@router.post("/items", response_model=WatchlistItemOut, status_code=201)
def add_watchlist_item(
    body: AddWatchlistItemRequest,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistItemOut:
    symbol = body.symbol.strip()
    try:
        validate_symbol_format(symbol)
    except InvalidSymbolError as exc:
        raise StockNotFoundError(str(exc)) from exc

    stock = session.query(Stock).filter(Stock.symbol == symbol).first()
    if stock is None:
        raise StockNotFoundError(f"لا يوجد سهم مسجل بالرمز '{symbol}'.")

    watchlist = _get_or_create_watchlist(session, current_user.id)

    existing = (
        session.query(UserWatchlistItem)
        .filter(UserWatchlistItem.watchlist_id == watchlist.id, UserWatchlistItem.stock_id == stock.id)
        .first()
    )
    if existing is not None:
        raise WatchlistItemAlreadyExistsError(f"السهم '{symbol}' موجود بالفعل في قائمة المتابعة.")

    item = UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol=stock.symbol)
    session.add(item)
    session.commit()

    latest = (
        session.query(DecisionV2Snapshot)
        .filter(DecisionV2Snapshot.symbol == symbol)
        .order_by(DecisionV2Snapshot.decision_timestamp.desc())
        .first()
    )
    radar = current_live_opportunity(session, symbol)
    return _item_out(item, stock, latest, radar)


@router.delete("/items/{symbol}", response_model=MessageOut)
def remove_watchlist_item(
    symbol: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    watchlist = _get_or_create_watchlist(session, current_user.id)
    item = (
        session.query(UserWatchlistItem)
        .filter(UserWatchlistItem.watchlist_id == watchlist.id, UserWatchlistItem.symbol == symbol)
        .first()
    )
    if item is None:
        raise WatchlistItemNotFoundError(f"السهم '{symbol}' غير موجود في قائمة المتابعة.")

    session.delete(item)
    session.commit()
    return MessageOut(message=f"تمت إزالة السهم '{symbol}' من قائمة المتابعة.")


def _news_alert_out(a: WatchlistNewsAlert) -> WatchlistNewsAlertOut:
    return WatchlistNewsAlertOut(
        id=a.id, watchlist_id=a.watchlist_id, symbol=a.symbol, news_event_id=a.news_event_id,
        alert_type=a.alert_type.value, severity=a.severity.value, message=a.message, message_ar=a.message_ar,
        generated_at=a.generated_at, acknowledged_at=a.acknowledged_at,
    )


@router.get("/news-alerts", response_model=WatchlistNewsAlertListOut)
def get_watchlist_news_alerts(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistNewsAlertListOut:
    """Already-persisted alerts for the caller's own watchlist -- see
    `POST .../news-alerts/refresh` to generate new ones from the
    latest news."""
    watchlist = _get_or_create_watchlist(session, current_user.id)
    rows = (
        session.query(WatchlistNewsAlert)
        .filter_by(watchlist_id=watchlist.id)
        .order_by(WatchlistNewsAlert.generated_at.desc())
        .all()
    )
    return WatchlistNewsAlertListOut(alerts=[_news_alert_out(a) for a in rows])


@router.post("/news-alerts/refresh", response_model=WatchlistNewsAlertListOut)
def refresh_watchlist_news_alerts(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistNewsAlertListOut:
    """Re-evaluates every symbol on the caller's watchlist against the
    latest analyzed news and persists any new Upgrade/Downgrade/High
    Risk/Major Opportunity alerts -- idempotent, never duplicates an
    alert already generated for the same (watchlist, news event) pair.
    Does not itself collect new news -- pair with
    `POST /api/v1/news/refresh` (or a scheduled job calling both) to
    pick up genuinely new articles first."""
    watchlist = _get_or_create_watchlist(session, current_user.id)
    symbols = [
        item.symbol
        for item in session.query(UserWatchlistItem).filter(UserWatchlistItem.watchlist_id == watchlist.id).all()
    ]

    alerts = WatchlistNewsAlertEngine().generate_and_persist(session, watchlist, symbols)
    return WatchlistNewsAlertListOut(
        alerts=[
            WatchlistNewsAlertOut(
                id=a.id, watchlist_id=a.watchlist_id, symbol=a.symbol, news_event_id=a.news_event_id,
                alert_type=a.alert_type.value, severity=a.severity.value, message=a.message, message_ar=a.message_ar,
                generated_at=a.generated_at, acknowledged_at=None,
            )
            for a in alerts
        ]
    )
