"""Momentary elevator call; periodic status is not an on/off state."""
from homeassistant.core import callback
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN
from .models import DeviceType


async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]

    @callback
    def add_device(dev):
        if dev.platform == Platform.BUTTON and dev.key.device_type == DeviceType.ELEVATOR:
            async_add_entities([NavienElevatorButton(gateway, dev)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_device)
    )


class NavienElevatorButton(ButtonEntity):
    _attr_should_poll = False
    _attr_name = "엘리베이터 호출"
    _attr_icon = "mdi:elevator"

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id

    async def async_press(self):
        await self.gateway.send(self._device.key, "call")
