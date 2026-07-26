"""Response/request schemas for /api/v1/admin/*."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class SetStaffRoleRequest(BaseModel):
    is_staff: bool
    staff_role: Optional[str] = Field(default=None, pattern="^(OWNER|ADMIN|SUPPORT)$")

    @model_validator(mode="after")
    def _staff_role_required_iff_is_staff(self) -> "SetStaffRoleRequest":
        if self.is_staff and self.staff_role is None:
            raise ValueError("staff_role is required when is_staff is true.")
        if not self.is_staff and self.staff_role is not None:
            raise ValueError("staff_role must be omitted when is_staff is false.")
        return self


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


class AdminPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: float
    status: str
    provider_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AdminInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: Optional[int] = None
    amount: float
    currency: str
    status: str
    provider: str
    provider_reference: Optional[str] = None
    issued_at: datetime
    paid_at: Optional[datetime] = None


class AdminInvoiceListOut(BaseModel):
    total: int
    invoices: List[AdminInvoiceOut]


class AdminPaymentListOut(BaseModel):
    payments: List[AdminPaymentOut]


class ExtendTrialRequest(BaseModel):
    additional_days: int = Field(gt=0, le=365)


class ActivateSubscriptionRequest(BaseModel):
    plan: str = Field(pattern="^(MONTHLY|YEARLY)$")
    period_days: int = Field(gt=0, le=366)


class CancelSubscriptionRequest(BaseModel):
    immediately: bool = False


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


class AdminDashboardSummaryOut(BaseModel):
    app_version: str
    deployment_commit: Optional[str] = None
    environment: str
    database_health: str
    redis_health: str
    ingestion_scheduler_running: bool
    market_intelligence_scheduler_running: bool
    market_data_provider: Optional[str] = None
    market_data_health: Optional[str] = None
    new_users_last_24h: int
    new_users_last_7d: int
    logins_last_24h: int
    locked_accounts: int
