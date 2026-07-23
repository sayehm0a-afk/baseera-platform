import pytest
from unittest.mock import MagicMock, patch
from enum import Enum
from datetime import datetime, timedelta, timezone
from src.core.autonomous_intelligence_layer.error_recovery.error_recovery import (
    ErrorRecovery, ErrorRecoveryConfig, ErrorRecord, RecoveryAction, ErrorSeverity, RetryStrategy
)

@pytest.fixture
def error_recovery_instance():
    return ErrorRecovery()

@pytest.fixture
def mock_recovery_func():
    mock = MagicMock(return_value="Recovery Successful")
    return mock

def test_error_recovery_init(error_recovery_instance):
    assert isinstance(error_recovery_instance.config, ErrorRecoveryConfig)
    assert not error_recovery_instance.errors
    assert not error_recovery_instance.recovery_actions
    assert not error_recovery_instance.error_history
    assert not error_recovery_instance.fallback_handlers

def test_record_error(error_recovery_instance):
    error = error_recovery_instance.record_error(
        "err1", "TypeError", "Invalid type", ErrorSeverity.ERROR, {"data": 123}
    )
    assert error is not None
    assert error.error_id == "err1"
    assert error.error_type == "TypeError"
    assert error.severity == ErrorSeverity.ERROR
    assert "err1" in error_recovery_instance.errors
    assert error in error_recovery_instance.error_history

def test_record_error_max_limit(error_recovery_instance):
    error_recovery_instance.config.max_errors = 1
    error_recovery_instance.record_error("err1", "Type", "Msg", ErrorSeverity.ERROR)
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.logger") as mock_logger:
        error = error_recovery_instance.record_error("err2", "Type", "Msg", ErrorSeverity.ERROR)
        assert error is None
        mock_logger.error.assert_called_once_with("Maximum errors limit reached", exc_info=True)

def test_create_recovery_action(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    action = error_recovery_instance.create_recovery_action("act1", "err1", "Retry")
    assert action is not None
    assert action.action_id == "act1"
    assert action.error_id == "err1"
    assert action.status == "PENDING"
    assert "act1" in error_recovery_instance.recovery_actions

def test_create_recovery_action_error_not_found(error_recovery_instance):
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.logger") as mock_logger:
        action = error_recovery_instance.create_recovery_action("act1", "nonexistent_err", "Retry")
        assert action is None
        mock_logger.error.assert_called_once_with("Error nonexistent_err not found", exc_info=True)

def test_execute_recovery_success(error_recovery_instance, mock_recovery_func):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    action = error_recovery_instance.create_recovery_action("act1", "err1", "Retry")
    success, result = error_recovery_instance.execute_recovery("act1", mock_recovery_func)
    assert success is True
    assert result == "Recovery Successful"
    assert action.status == "SUCCESS"
    mock_recovery_func.assert_called_once()

def test_execute_recovery_failure_no_retries(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    action = error_recovery_instance.create_recovery_action("act1", "err1", "Retry")
    mock_func = MagicMock(side_effect=Exception("Failed"))
    error_recovery_instance.config.max_retries = 0
    success, result = error_recovery_instance.execute_recovery("act1", mock_func)
    assert success is False
    assert result is None
    assert action.status == "FAILED"
    assert mock_func.call_count == 1

def test_execute_recovery_with_retries(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    action = error_recovery_instance.create_recovery_action("act1", "err1", "Retry")
    mock_func = MagicMock(side_effect=[Exception("Attempt 1"), Exception("Attempt 2"), "Success after retry"])
    error_recovery_instance.config.max_retries = 2
    error_recovery_instance.config.initial_retry_delay_seconds = 0 # No actual sleep in test

    success, result = error_recovery_instance.execute_recovery("act1", mock_func)
    assert success is True
    assert result == "Success after retry"
    assert action.status == "SUCCESS"
    assert mock_func.call_count == 3
    assert action.attempts == 3

def test_calculate_retry_delay_immediate(error_recovery_instance):
    delay = error_recovery_instance._calculate_retry_delay(0, RetryStrategy.IMMEDIATE)
    assert delay == 0

def test_calculate_retry_delay_linear_backoff(error_recovery_instance):
    error_recovery_instance.config.initial_retry_delay_seconds = 10
    delay = error_recovery_instance._calculate_retry_delay(0, RetryStrategy.LINEAR_BACKOFF)
    assert delay == 10
    delay = error_recovery_instance._calculate_retry_delay(1, RetryStrategy.LINEAR_BACKOFF)
    assert delay == 20

def test_calculate_retry_delay_exponential_backoff(error_recovery_instance):
    error_recovery_instance.config.initial_retry_delay_seconds = 5
    delay = error_recovery_instance._calculate_retry_delay(0, RetryStrategy.EXPONENTIAL_BACKOFF)
    assert delay == 5
    delay = error_recovery_instance._calculate_retry_delay(1, RetryStrategy.EXPONENTIAL_BACKOFF)
    assert delay == 10
    delay = error_recovery_instance._calculate_retry_delay(2, RetryStrategy.EXPONENTIAL_BACKOFF)
    assert delay == 20

def test_calculate_retry_delay_fibonacci_backoff(error_recovery_instance):
    error_recovery_instance.config.initial_retry_delay_seconds = 1
    delay = error_recovery_instance._calculate_retry_delay(0, RetryStrategy.FIBONACCI_BACKOFF)
    assert delay == 1
    delay = error_recovery_instance._calculate_retry_delay(1, RetryStrategy.FIBONACCI_BACKOFF)
    assert delay == 1
    delay = error_recovery_instance._calculate_retry_delay(2, RetryStrategy.FIBONACCI_BACKOFF)
    assert delay == 2
    delay = error_recovery_instance._calculate_retry_delay(9, RetryStrategy.FIBONACCI_BACKOFF)
    assert delay == 55 # Max fib value in list
    delay = error_recovery_instance._calculate_retry_delay(10, RetryStrategy.FIBONACCI_BACKOFF)
    assert delay == 55 # Should cap at max fib value

def test_calculate_retry_delay_unknown_strategy(error_recovery_instance):
    error_recovery_instance.config.initial_retry_delay_seconds = 7
    # Mock an unknown strategy
    class UnknownStrategy(Enum):
        UNKNOWN = "unknown"
    delay = error_recovery_instance._calculate_retry_delay(0, UnknownStrategy.UNKNOWN)
    assert delay == 7

def test_calculate_retry_delay_capped(error_recovery_instance):
    error_recovery_instance.config.initial_retry_delay_seconds = 100
    error_recovery_instance.config.max_retry_delay_seconds = 150
    delay = error_recovery_instance._calculate_retry_delay(1, RetryStrategy.LINEAR_BACKOFF)
    assert delay == 150 # 100 * (1+1) = 200, capped at 150

def test_register_fallback_handler(error_recovery_instance):
    def fallback_func(): return "Fallback result"
    registered = error_recovery_instance.register_fallback_handler("ConnectionError", fallback_func)
    assert registered is True
    assert "ConnectionError" in error_recovery_instance.fallback_handlers

def test_execute_fallback_success(error_recovery_instance):
    def fallback_func(): return "Fallback result"
    error_recovery_instance.register_fallback_handler("ConnectionError", fallback_func)
    result = error_recovery_instance.execute_fallback("ConnectionError")
    assert result == "Fallback result"

def test_execute_fallback_not_found(error_recovery_instance):
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.logger") as mock_logger:
        result = error_recovery_instance.execute_fallback("NonExistentError")
        assert result is None
        mock_logger.warning.assert_called_once_with("No fallback handler for error type: NonExistentError")

def test_execute_fallback_exception(error_recovery_instance):
    def failing_fallback_func(): raise Exception("Fallback failed")
    error_recovery_instance.register_fallback_handler("FailingError", failing_fallback_func)
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.logger") as mock_logger:
        result = error_recovery_instance.execute_fallback("FailingError")
        assert result is None
        mock_logger.error.assert_called_once_with("Fallback execution failed: Fallback failed", exc_info=True)

def test_get_error(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    retrieved_error = error_recovery_instance.get_error("err1")
    assert retrieved_error is not None
    assert retrieved_error.error_id == "err1"
    assert error_recovery_instance.get_error("nonexistent") is None

def test_get_recovery_action(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    error_recovery_instance.create_recovery_action("act1", "err1", "Retry")
    retrieved_action = error_recovery_instance.get_recovery_action("act1")
    assert retrieved_action is not None
    assert retrieved_action.action_id == "act1"
    assert error_recovery_instance.get_recovery_action("nonexistent") is None

def test_get_error_history(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    error_recovery_instance.record_error("err2", "ValueError", "Invalid value", ErrorSeverity.WARNING)
    history = error_recovery_instance.get_error_history()
    assert len(history) == 2
    assert history[0].error_id == "err1"
    assert history[1].error_id == "err2"

def test_get_errors_by_severity(error_recovery_instance):
    error_recovery_instance.record_error("err1", "TypeError", "Invalid type", ErrorSeverity.ERROR)
    error_recovery_instance.record_error("err2", "ValueError", "Invalid value", ErrorSeverity.WARNING)
    error_recovery_instance.record_error("err3", "ConnectionError", "No conn", ErrorSeverity.ERROR)
    errors = error_recovery_instance.get_errors_by_severity(ErrorSeverity.ERROR)
    assert len(errors) == 2
    assert errors[0].error_id == "err1"
    assert errors[1].error_id == "err3"

def test_get_recent_errors(error_recovery_instance):
    # Record an old error
    old_timestamp = datetime.now(timezone.utc) - timedelta(minutes=70)
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.datetime") as mock_dt:
        mock_dt.now.return_value = old_timestamp
        mock_dt.side_effect = lambda *args, **kw: datetime.now(timezone.utc) if args else datetime(1, 1, 1, tzinfo=timezone.utc)
        error_recovery_instance.record_error("old_err", "OldError", "Old message", ErrorSeverity.INFO)

    # Record a recent error
    recent_timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
    with patch("src.core.autonomous_intelligence_layer.error_recovery.error_recovery.datetime") as mock_dt:
        mock_dt.now.return_value = recent_timestamp
        mock_dt.side_effect = lambda *args, **kw: datetime.now(timezone.utc) if args else datetime(1, 1, 1, tzinfo=timezone.utc)
        error_recovery_instance.record_error("recent_err", "RecentError", "Recent message", ErrorSeverity.WARNING)

    recent_errors = error_recovery_instance.get_recent_errors(minutes=60)
    assert len(recent_errors) == 1
    assert recent_errors[0].error_id == "recent_err"

    all_errors = error_recovery_instance.get_recent_errors(minutes=100)
    assert len(all_errors) == 2
