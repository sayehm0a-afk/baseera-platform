"""GET/POST/PATCH /api/v1/admin/feature-flags/* -- manage runtime
on/off switches (see FeatureFlag's own docstring for how this differs
from env-level Settings)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.admin.audit_log import record_admin_action
from src.admin.exceptions import FeatureFlagAlreadyExistsError, FeatureFlagNotFoundError
from src.api.schemas.admin import FeatureFlagCreateRequest, FeatureFlagListOut, FeatureFlagOut, FeatureFlagUpdateRequest
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import FeatureFlag, StaffRole, User

router = APIRouter(prefix="/api/v1/admin/feature-flags", tags=["admin"])


def _client_ip(request: Request) -> "str | None":
    return request.client.host if request.client else None


def _get_flag_or_404(session: Session, key: str) -> FeatureFlag:
    flag = session.query(FeatureFlag).filter_by(key=key).one_or_none()
    if flag is None:
        raise FeatureFlagNotFoundError(f"No feature flag {key!r}.")
    return flag


@router.get("", response_model=FeatureFlagListOut)
def list_feature_flags(
    session: Session = Depends(get_db), _current_user: User = Depends(require_staff_role(StaffRole.ADMIN))
) -> FeatureFlagListOut:
    rows = session.query(FeatureFlag).order_by(FeatureFlag.key).all()
    return FeatureFlagListOut(feature_flags=[FeatureFlagOut.model_validate(r) for r in rows])


@router.post("", response_model=FeatureFlagOut, status_code=201)
def create_feature_flag(
    body: FeatureFlagCreateRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> FeatureFlagOut:
    if session.query(FeatureFlag).filter_by(key=body.key).one_or_none() is not None:
        raise FeatureFlagAlreadyExistsError(f"Feature flag {body.key!r} already exists.")

    flag = FeatureFlag(key=body.key, enabled=body.enabled, description=body.description)
    session.add(flag)
    session.commit()
    record_admin_action(
        session, current_user.id, "feature_flag.create", "feature_flag", details={"key": body.key},
        ip_address=_client_ip(request),
    )
    return FeatureFlagOut.model_validate(flag)


@router.patch("/{key}", response_model=FeatureFlagOut)
def update_feature_flag(
    key: str,
    body: FeatureFlagUpdateRequest,
    request: Request,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> FeatureFlagOut:
    flag = _get_flag_or_404(session, key)
    flag.enabled = body.enabled
    session.commit()
    record_admin_action(
        session, current_user.id, "feature_flag.update", "feature_flag", details={"key": key, "enabled": body.enabled},
        ip_address=_client_ip(request),
    )
    return FeatureFlagOut.model_validate(flag)
