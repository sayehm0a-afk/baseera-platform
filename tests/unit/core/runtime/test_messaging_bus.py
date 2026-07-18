import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from core.runtime.messaging_bus import MessagingBus

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.messaging_bus").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_dispatcher").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_router").setLevel(logging.INFO)

@pytest.fixture
def messaging_bus():
    return MessagingBus()

@pytest.mark.asyncio
async def test_messaging_bus_publish_event(messaging_bus):
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    await messaging_bus.register_event_handler("test_event", handler1)
    await messaging_bus.register_event_handler("test_event", handler2)
    payload = {"data": "test"}
    await messaging_bus.publish_event("test_event", payload)
    handler1.assert_called_once_with(payload)
    handler2.assert_called_once_with(payload)

@pytest.mark.asyncio
async def test_messaging_bus_publish_event_no_handlers(messaging_bus, caplog):
    payload = {"data": "test"}
    await messaging_bus.publish_event("non_existent_event", payload)
    assert "Publishing event" in caplog.text
    assert "non_existent_event" in caplog.text
    assert "test" in caplog.text

@pytest.mark.asyncio
async def test_messaging_bus_publish_event_handler_raises_exception(messaging_bus, caplog):
    handler = AsyncMock(side_effect=Exception("Handler error"))
    await messaging_bus.register_event_handler("error_event", handler)
    payload = {"data": "error"}
    await messaging_bus.publish_event("error_event", payload)
    handler.assert_called_once_with(payload)
    assert "Error handling event" in caplog.text
    assert "error_event" in caplog.text
    assert "Handler error" in caplog.text

@pytest.mark.asyncio
async def test_messaging_bus_send_command(messaging_bus):
    handler = AsyncMock(return_value="Command Result")
    await messaging_bus.register_command_handler("test_command", handler)
    payload = {"action": "do_something"}
    result = await messaging_bus.send_command("test_command", payload)
    handler.assert_called_once_with(payload)
    assert result == "Command Result"

@pytest.mark.asyncio
async def test_messaging_bus_send_command_no_handler(messaging_bus):
    payload = {"action": "do_something"}
    with pytest.raises(ValueError, match="No handler registered for command non_existent_command"):
        await messaging_bus.send_command("non_existent_command", payload)

@pytest.mark.asyncio
async def test_messaging_bus_send_command_handler_raises_exception(messaging_bus, caplog):
    handler = AsyncMock(side_effect=ValueError("Command processing error"))
    await messaging_bus.register_command_handler("error_command", handler)
    payload = {"action": "fail"}
    with pytest.raises(ValueError, match="Command processing error"):
        await messaging_bus.send_command("error_command", payload)
    handler.assert_called_once_with(payload)
    assert "Error handling command" in caplog.text
    assert "error_command" in caplog.text
    assert "Command processing error" in caplog.text

@pytest.mark.asyncio
async def test_messaging_bus_register_event_handler(messaging_bus, caplog):
    handler = AsyncMock()
    await messaging_bus.register_event_handler("new_event", handler)
    assert "Registered event handler for" in caplog.text
    assert "new_event" in caplog.text
    assert handler in messaging_bus._event_handlers["new_event"]

@pytest.mark.asyncio
async def test_messaging_bus_register_command_handler(messaging_bus, caplog):
    handler = AsyncMock()
    await messaging_bus.register_command_handler("new_command", handler)
    assert "Registered command handler for" in caplog.text
    assert "new_command" in caplog.text
    assert messaging_bus._command_handlers["new_command"] == handler

@pytest.mark.asyncio
async def test_messaging_bus_register_command_handler_overwrite(messaging_bus, caplog):
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    await messaging_bus.register_command_handler("overwrite_command", handler1)
    await messaging_bus.register_command_handler("overwrite_command", handler2)
    assert "Command handler already registered for" in caplog.text
    assert "overwrite_command" in caplog.text
    assert "Overwriting." in caplog.text
    assert messaging_bus._command_handlers["overwrite_command"] == handler2
