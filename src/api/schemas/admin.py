"""Response/request schemas for /api/v1/admin/*."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_email_verified: bool
    is_active: bool
    is_staff: bool
    staff_role: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class AdminUserListOut(BaseModel):
    total: int
    users: List[AdminUserOut]


class AdminSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan: str
    status: str
    trial_ends_at: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool


class AdminSubscriptionListOut(BaseModel):
    total: int
    subscriptions: List[AdminSubscriptionOut]


class ExtendTrialRequest(BaseModel):
    additional_days: int = Field(gt=0, le=365)


class ActivateSubscriptionRequest(BaseModel):
    plan: str = Field(pattern="^(MONTHLY|YEARLY)$")
    period_days: int = Field(gt=0, le=366)


class AdminSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    device_label: Optional[str] = None
    ip_address: Optional[str] = None
    issued_at: datetime
    last_used_at: datetime
    expires_at: datetime


class AdminSessionListOut(BaseModel):
    total: int
    sessions: List[AdminSessionOut]


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    severity: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    is_active: bool
    created_by_user_id: int
    created_at: datetime


class AnnouncementListOut(BaseModel):
    announcements: List[AnnouncementOut]


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    severity: str = Field(default="INFO", pattern="^(INFO|WARNING|CRITICAL)$")
    starts_at: datetime
    ends_at: Optional[datetime] = None


class AnnouncementUpdateRequest(BaseModel):
    is_active: Optional[bool] = None


class FeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    enabled: bool
    description: Optional[str] = None


class FeatureFlagListOut(BaseModel):
    feature_flags: List[FeatureFlagOut]


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    enabled: bool = False
    description: Optional[str] = None


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int
    action: str
    target_type: str
    target_id: Optional[int] = None
    details_json: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime


class AuditLogListOut(BaseModel):
    total: int
    logs: List[AuditLogOut]


class AIUsageSummaryOut(BaseModel):
    total_requests: int
    success_count: int
    failed_count: int
    timeout_count: int
    total_tokens: int
    estimated_cost_usd: float
    by_feature: Dict[str, int]


class AnalyticsOut(BaseModel):
    total_users: int
    users_by_staff_role: Dict[str, int]
    subscriptions_by_status: Dict[str, int]
    subscriptions_by_plan: Dict[str, int]
    total_portfolios: int
    total_backtest_runs: int


class SystemHealthOut(BaseModel):
    status: str
    details: Dict[str, Any]
