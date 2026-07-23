import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.message_router import MessageRouter
from src.core.runtime.messaging_bus import MessagingBus
from src.core.runtime.message_dispatcher import MessageDispatcher


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.messaging_bus").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_dispatcher").setLevel(logging.INFO)
    logging.getLogger("src.core.runtime.message_router").setLevel(logging.INFO)


@pytest.fixture
def message_router():
    return MessageRouter()


@pytest.fixture
def mock_messaging_bus():
    mock_bus = AsyncMock(spec=MessagingBus)
    return mock_bus


@pytest.fixture
def mock_message_dispatcher():
    mock_dispatcher = AsyncMock(spec=MessageDispatcher)
    return mock_dispatcher


@pytest.mark.asyncio
async def test_message_router_route_message_to_dispatcher(message_router, mock_message_dispatcher):
    message_type = "command.test"
    payload = {"action": "do_something"}
    mock_message_dispatcher.dispatch.return_value = "Dispatcher Result"

    await message_router.register_route(message_type, mock_message_dispatcher)
    result = await message_router.route_message(message_type, payload)

    mock_message_dispatcher.dispatch.assert_called_once_with(message_type, payload)
    assert result == "Dispatcher Result"


@pytest.mark.asyncio
async def test_message_router_route_message_to_bus_publish_event(message_router, mock_messaging_bus):
    message_type = "event.test"
    payload = {"data": "event_data"}
    mock_messaging_bus.publish_event.return_value = None

    await message_router.register_route(message_type, mock_messaging_bus)
    result = await message_router.route_message(message_type, payload)

    mock_messaging_bus.publish_event.assert_called_once_with(message_type, payload)
    assert result is None


@pytest.mark.asyncio
async def test_message_router_route_message_to_bus_send_command(message_router, mock_messaging_bus):
    message_type = "command.bus_test"
    payload = {"action": "bus_command"}
    mock_messaging_bus.send_command.return_value = "Bus Command Result"
    del mock_messaging_bus.publish_event

    await message_router.register_route(message_type, mock_messaging_bus)
    result = await message_router.route_message(message_type, payload)

    assert result == "Bus Command Result"
    mock_messaging_bus.send_command.assert_called_once_with(message_type, payload)


@pytest.mark.asyncio
async def test_message_router_route_message_no_route(message_router):
    message_type = "non_existent_message"
    payload = {"data": "some_data"}

    with pytest.raises(ValueError, match=f"No route registered for message {message_type}"):
        await message_router.route_message(message_type, payload)


@pytest.mark.asyncio
async def test_message_router_route_message_invalid_destination(message_router, caplog):
    message_type = "invalid.destination"
    payload = {"data": "invalid"}
    invalid_destination = MagicMock(spec=[]) # Ensure it has no dispatch, publish_event, or send_command methods

    await message_router.register_route(message_type, invalid_destination)
    with pytest.raises(TypeError, match=f"Invalid destination type for message {message_type}"):
        await message_router.route_message(message_type, payload)
    assert "Invalid destination type for message" in caplog.text


@pytest.mark.asyncio
async def test_message_router_register_route(message_router, mock_message_dispatcher, caplog):
    message_type = "new.route"
    await message_router.register_route(message_type, mock_message_dispatcher)
    assert "Registered route for message" in caplog.text
    assert message_type in message_router._routes
    assert message_router._routes[message_type] == mock_message_dispatcher


@pytest.mark.asyncio
async def test_message_router_register_route_overwrite(message_router, mock_message_dispatcher, mock_messaging_bus, caplog):
    message_type = "overwrite.route"
    await message_router.register_route(message_type, mock_message_dispatcher)
    await message_router.register_route(message_type, mock_messaging_bus)
    assert "Route already registered for message" in caplog.text
    assert "Overwriting." in caplog.text
    assert message_router._routes[message_type] == mock_messaging_bus
