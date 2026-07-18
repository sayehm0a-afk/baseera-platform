import pytest
from unittest.mock import MagicMock, patch
import logging
from core.runtime.observability_layer.logging_manager import LoggingManager, ILoggingManager

@pytest.fixture
def logging_manager() -> ILoggingManager:


    return LoggingManager()

@pytest.mark.asyncio
async def test_get_logger(logging_manager: ILoggingManager):
    logger_name = "test_logger"
    logger = logging_manager.get_logger(logger_name)

    assert isinstance(logger, logging.Logger)
    assert logger.name == logger_name
    assert logger.propagate is True

    # Ensure getting the same logger returns the same instance
    another_logger = logging_manager.get_logger(logger_name)
    assert logger is another_logger

@pytest.mark.asyncio
async def test_configure_logging_default(logging_manager: ILoggingManager, caplog):
    # LoggingManager is initialized with default logging, so we just need to check it
    logger = logging_manager.get_logger("default_test")
    with caplog.at_level(logging.INFO):
        logger.info("This is a test message")

    assert "This is a test message" in caplog.text
    assert "INFO" in caplog.text

@pytest.mark.asyncio
async def test_configure_logging_custom_level(logging_manager: ILoggingManager, capsys):
    logging_manager.configure_logging(level="DEBUG")
    logger = logging_manager.get_logger("debug_logger")
    logger.debug("Debug message")
    logger.info("Info message")

    captured = capsys.readouterr()
    assert "Debug message" in captured.out
    assert "Info message" in captured.out
    assert "DEBUG" in captured.out

@pytest.mark.asyncio
async def test_configure_logging_custom_handler(logging_manager: ILoggingManager):
    mock_handler = MagicMock(spec=logging.Handler)
    mock_handler.level = logging.INFO
    logging_manager.configure_logging(handlers=[mock_handler])

    logger = logging_manager.get_logger("custom_handler_logger")
    logger.info("Message to custom handler")

    mock_handler.handle.assert_called_once()
    assert "Message to custom handler" in mock_handler.handle.call_args[0][0].getMessage()

@pytest.mark.asyncio
async def test_configure_logging_clears_old_handlers(logging_manager: ILoggingManager, capsys):
    # Configure with a custom handler first
    mock_handler_old = MagicMock(spec=logging.Handler)
    mock_handler_old.level = logging.INFO
    logging_manager.configure_logging(handlers=[mock_handler_old])
    logger_old = logging_manager.get_logger("old_logger")
    logger_old.info("Old message")
    mock_handler_old.handle.assert_called_once()
    mock_handler_old.reset_mock()

    # Reconfigure with default handlers (no custom handlers provided)
    logging_manager.configure_logging()
    logger_new = logging_manager.get_logger("new_logger")
    logger_new.info("New message")

    # Old handler should not have been called again
    mock_handler_old.handle.assert_not_called()
    
    # New message should go to console
    captured = capsys.readouterr()
    assert "New message" in captured.out

@pytest.mark.asyncio
async def test_logger_propagation(logging_manager: ILoggingManager):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    mock_root_handler = MagicMock(spec=logging.Handler)
    mock_root_handler.level = logging.DEBUG
    root_logger.addHandler(mock_root_handler)

    logger = logging_manager.get_logger("propagating_logger")
    assert logger.propagate is True

    logger.info("Test message for propagating logger")
    mock_root_handler.handle.assert_called_once()
    assert "Test message for propagating logger" in mock_root_handler.handle.call_args[0][0].getMessage()

    root_logger.removeHandler(mock_root_handler)
