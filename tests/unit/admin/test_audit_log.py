import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.admin.audit_log import list_admin_actions, record_admin_action
from src.core.db.database import Base
from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import User


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_user(session):
    u = User(email="admin@example.com", password_hash="hashed", is_staff=True)
    session.add(u)
    session.commit()
    return u


def test_record_admin_action_persists_every_field(session, admin_user):
    log = record_admin_action(
        session,
        admin_user.id,
        "user.suspend",
        "user",
        target_id=99,
        details={"reason": "fraud"},
        ip_address="127.0.0.1",
    )
    assert log.id is not None
    assert log.action == "user.suspend"
    assert log.details_json == {"reason": "fraud"}


def test_list_admin_actions_filters_by_actor_and_action(session, admin_user):
    other_admin = User(email="admin2@example.com", password_hash="hashed", is_staff=True)
    session.add(other_admin)
    session.commit()

    record_admin_action(session, admin_user.id, "user.suspend", "user", target_id=1)
    record_admin_action(session, admin_user.id, "user.unsuspend", "user", target_id=1)
    record_admin_action(session, other_admin.id, "user.suspend", "user", target_id=2)

    total, logs = list_admin_actions(session, limit=50, offset=0)
    assert total == 3

    total, logs = list_admin_actions(session, limit=50, offset=0, actor_user_id=admin_user.id)
    assert total == 2

    total, logs = list_admin_actions(session, limit=50, offset=0, action="user.suspend")
    assert total == 2


def test_record_admin_action_updates_prometheus_counter(session, admin_user):
    metrics = get_metrics()
    before = metrics.admin_actions_total.labels(action="metrics_check_action")._value.get()

    record_admin_action(session, admin_user.id, "metrics_check_action", "user", target_id=1)

    assert metrics.admin_actions_total.labels(action="metrics_check_action")._value.get() == before + 1
