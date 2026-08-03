"""Aggregates every /api/v1/admin/* router into one `router` so
main.py only needs a single `app.include_router(admin_router)` --
each sub-module keeps its own file (users/subscriptions/sessions/
announcements/feature_flags/audit_log/usage/analytics/system/billing),
one capability area per the Phase 10 Admin Dashboard spec, per file.
"""

from fastapi import APIRouter

from src.api.routes.admin import (
    ai_evolution,
    analytics,
    announcements,
    audit_log,
    billing,
    feature_flags,
    market_intelligence,
    sessions,
    subscriptions,
    system,
    usage,
    users,
)

router = APIRouter()
router.include_router(users.router)
router.include_router(subscriptions.router)
router.include_router(sessions.router)
router.include_router(announcements.router)
router.include_router(feature_flags.router)
router.include_router(audit_log.router)
router.include_router(usage.router)
router.include_router(analytics.router)
router.include_router(system.router)
router.include_router(billing.router)
router.include_router(ai_evolution.router)
router.include_router(market_intelligence.router)
