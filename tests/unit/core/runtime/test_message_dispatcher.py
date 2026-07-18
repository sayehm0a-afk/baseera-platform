import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from core.runtime.message_dispatcher import MessageDispatcher

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.messaging_bus").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_dispatcher").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_router").setLevel(logging.INFO)

@pytest.fixture
def message_dispatcher():
    return MessageDispatcher()

@pytest.mark.asyncio
async def test_message_dispatcher_dispatch(message_dispatcher):
    handler = AsyncMock(return_value="Dispatch Result")
    await message_dispatcher.register_handler("test_message", handler)
    payload = {"data": "dispatch_test"}
    result = await message_dispatcher.dispatch("test_message", payload)
    handler.assert_called_once_with(payload)
    assert result == "Dispatch Result"

@pytest.mark.asyncio
async def test_message_dispatcher_dispatch_no_handler(message_dispatcher):
    payload = {"data": "dispatch_test"}
    with pytest.raises(ValueError, match="No handler registered for message non_existent_message"):
        await message_dispatcher.dispatch("non_existent_message", payload)

@pytest.mark.asyncio
async def test_message_dispatcher_dispatch_handler_raises_exception(message_dispatcher, caplog):
    handler = AsyncMock(side_effect=Exception("Dispatch error"))
    await message_dispatcher.register_handler("error_message", handler)
    payload = {"data": "error"}
    with pytest.raises(Exception, match="Dispatch error"):
        await message_dispatcher.dispatch("error_message", payload)
    handler.assert_called_once_with(payload)
    assert "Error handling message" in caplog.text
    assert "error_message" in caplog.text
    assert "Dispatch error" in caplog.text

@pytest.mark.asyncio
async def test_message_dispatcher_register_handler(message_dispatcher, caplog):
    handler = AsyncMock()
    await message_dispatcher.register_handler("new_message", handler)
    assert "Registered handler for message" in caplog.text
    assert "new_message" in caplog.text
    assert message_dispatcher._handlers["new_message"] == handler

@pytest.mark.asyncio
async def test_message_dispatcher_register_handler_overwrite(message_dispatcher, caplog):
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    await message_dispatcher.register_handler("overwrite_message", handler1)
    await message_dispatcher.register_handler("overwrite_message", handler2)
    assert "Handler already registered for message" in caplog.text
    assert "overwrite_message" in caplog.text
    assert "Overwriting." in caplog.text
    assert message_dispatcher._handlers["overwrite_message"] == handler2
