"""
Unit tests for Error Recovery
"""

import pytest
from core.autonomous_intelligence_layer.error_recovery import (
    ErrorRecovery,
    ErrorSeverity,
    RetryStrategy,
    ErrorRecoveryConfig,
)


class TestErrorRecovery:
    """Test cases for ErrorRecovery class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recovery = ErrorRecovery()

    def test_error_recovery_initialization(self):
        """Test that ErrorRecovery initializes correctly."""
        assert self.recovery is not None
        assert self.recovery.config is not None
        assert isinstance(self.recovery.config, ErrorRecoveryConfig)

    def test_error_recovery_with_custom_config(self):
        """Test ErrorRecovery with custom config."""
        custom_config = ErrorRecoveryConfig(
            default_retry_strategy=RetryStrategy.LINEAR_BACKOFF,
            max_retries=5,
        )
        recovery = ErrorRecovery(config=custom_config)
        assert recovery.config.max_retries == 5

    def test_record_error(self):
        """Test recording an error."""
        error = self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value provided",
            severity=ErrorSeverity.ERROR,
        )

        assert error is not None
        assert error.error_type == "ValueError"
        assert error.severity == ErrorSeverity.ERROR

    def test_record_error_with_context(self):
        """Test recording error with context."""
        context = {"agent_id": "agent_1", "operation": "process_data"}
        error = self.recovery.record_error(
            error_id="error_001",
            error_type="RuntimeError",
            message="Runtime error occurred",
            severity=ErrorSeverity.CRITICAL,
            context=context,
        )

        assert error is not None
        assert error.context == context

    def test_create_recovery_action(self):
        """Test creating a recovery action."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value",
            severity=ErrorSeverity.ERROR,
        )

        action = self.recovery.create_recovery_action(
            action_id="action_001",
            error_id="error_001",
            action_type="retry",
        )

        assert action is not None
        assert action.status == "PENDING"

    def test_create_recovery_action_invalid_error(self):
        """Test creating recovery action for nonexistent error."""
        action = self.recovery.create_recovery_action(
            action_id="action_001",
            error_id="nonexistent",
            action_type="retry",
        )

        assert action is None

    def test_execute_recovery_success(self):
        """Test executing recovery action successfully."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value",
            severity=ErrorSeverity.ERROR,
        )

        self.recovery.create_recovery_action(
            action_id="action_001",
            error_id="error_001",
            action_type="retry",
        )

        def recovery_func():
            return "recovered"

        success, result = self.recovery.execute_recovery(
            action_id="action_001",
            recovery_func=recovery_func,
        )

        assert success is True
        assert result == "recovered"

    def test_execute_recovery_failure(self):
        """Test executing recovery action with failure."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value",
            severity=ErrorSeverity.ERROR,
        )

        self.recovery.create_recovery_action(
            action_id="action_001",
            error_id="error_001",
            action_type="retry",
        )

        def recovery_func():
            raise ValueError("Recovery failed")

        success, result = self.recovery.execute_recovery(
            action_id="action_001",
            recovery_func=recovery_func,
        )

        assert success is False

    def test_register_fallback_handler(self):
        """Test registering a fallback handler."""
        def fallback_handler():
            return "fallback_result"

        result = self.recovery.register_fallback_handler(
            error_type="ValueError",
            handler=fallback_handler,
        )

        assert result is True

    def test_execute_fallback(self):
        """Test executing fallback handler."""
        def fallback_handler():
            return "fallback_result"

        self.recovery.register_fallback_handler(
            error_type="ValueError",
            handler=fallback_handler,
        )

        result = self.recovery.execute_fallback("ValueError")
        assert result == "fallback_result"

    def test_execute_fallback_not_found(self):
        """Test executing fallback for nonexistent error type."""
        result = self.recovery.execute_fallback("NonexistentError")
        assert result is None

    def test_get_error(self):
        """Test retrieving an error."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value",
            severity=ErrorSeverity.ERROR,
        )

        error = self.recovery.get_error("error_001")
        assert error is not None
        assert error.error_type == "ValueError"

    def test_get_recovery_action(self):
        """Test retrieving a recovery action."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Invalid value",
            severity=ErrorSeverity.ERROR,
        )

        self.recovery.create_recovery_action(
            action_id="action_001",
            error_id="error_001",
            action_type="retry",
        )

        action = self.recovery.get_recovery_action("action_001")
        assert action is not None

    def test_get_error_history(self):
        """Test getting error history."""
        for i in range(5):
            self.recovery.record_error(
                error_id=f"error_{i:03d}",
                error_type="ValueError",
                message=f"Error {i}",
                severity=ErrorSeverity.ERROR,
            )

        history = self.recovery.get_error_history()
        assert len(history) == 5

    def test_get_errors_by_severity(self):
        """Test getting errors by severity."""
        for i in range(3):
            self.recovery.record_error(
                error_id=f"error_{i:03d}",
                error_type="ValueError",
                message=f"Error {i}",
                severity=ErrorSeverity.ERROR,
            )

        for i in range(2):
            self.recovery.record_error(
                error_id=f"critical_{i:03d}",
                error_type="RuntimeError",
                message=f"Critical {i}",
                severity=ErrorSeverity.CRITICAL,
            )

        errors = self.recovery.get_errors_by_severity(ErrorSeverity.ERROR)
        assert len(errors) == 3

    def test_retry_strategy_immediate(self):
        """Test immediate retry strategy."""
        delay = self.recovery._calculate_retry_delay(0, RetryStrategy.IMMEDIATE)
        assert delay == 0

    def test_retry_strategy_linear_backoff(self):
        """Test linear backoff retry strategy."""
        delay0 = self.recovery._calculate_retry_delay(0, RetryStrategy.LINEAR_BACKOFF)
        delay1 = self.recovery._calculate_retry_delay(1, RetryStrategy.LINEAR_BACKOFF)
        delay2 = self.recovery._calculate_retry_delay(2, RetryStrategy.LINEAR_BACKOFF)

        assert delay1 > delay0
        assert delay2 > delay1

    def test_retry_strategy_exponential_backoff(self):
        """Test exponential backoff retry strategy."""
        delay0 = self.recovery._calculate_retry_delay(0, RetryStrategy.EXPONENTIAL_BACKOFF)
        delay1 = self.recovery._calculate_retry_delay(1, RetryStrategy.EXPONENTIAL_BACKOFF)
        delay2 = self.recovery._calculate_retry_delay(2, RetryStrategy.EXPONENTIAL_BACKOFF)

        assert delay1 > delay0
        assert delay2 > delay1
        # Exponential should grow faster than linear
        assert (delay2 - delay1) > (delay1 - delay0)

    def test_retry_strategy_fibonacci_backoff(self):
        """Test Fibonacci backoff retry strategy."""
        delay0 = self.recovery._calculate_retry_delay(0, RetryStrategy.FIBONACCI_BACKOFF)
        delay1 = self.recovery._calculate_retry_delay(1, RetryStrategy.FIBONACCI_BACKOFF)
        delay2 = self.recovery._calculate_retry_delay(2, RetryStrategy.FIBONACCI_BACKOFF)

        assert delay0 > 0
        assert delay1 >= delay0
        assert delay2 >= delay1

    def test_error_severity_levels(self):
        """Test different error severity levels."""
        severities = [
            ErrorSeverity.INFO,
            ErrorSeverity.WARNING,
            ErrorSeverity.ERROR,
            ErrorSeverity.CRITICAL,
        ]

        for i, severity in enumerate(severities):
            self.recovery.record_error(
                error_id=f"error_{i:03d}",
                error_type="TestError",
                message=f"Error {severity.value}",
                severity=severity,
            )

        for severity in severities:
            errors = self.recovery.get_errors_by_severity(severity)
            assert len(errors) == 1

    def test_multiple_recovery_actions(self):
        """Test handling multiple recovery actions."""
        self.recovery.record_error(
            error_id="error_001",
            error_type="ValueError",
            message="Error",
            severity=ErrorSeverity.ERROR,
        )

        for i in range(3):
            self.recovery.create_recovery_action(
                action_id=f"action_{i:03d}",
                error_id="error_001",
                action_type="retry",
            )

        assert len(self.recovery.recovery_actions) == 3

    def test_recent_errors(self):
        """Test getting recent errors."""
        for i in range(5):
            self.recovery.record_error(
                error_id=f"error_{i:03d}",
                error_type="ValueError",
                message=f"Error {i}",
                severity=ErrorSeverity.ERROR,
            )

        recent = self.recovery.get_recent_errors(minutes=60)
        assert len(recent) == 5
