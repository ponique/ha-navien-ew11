from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN
from .models import DeviceType

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_device(dev):
        if dev.platform == Platform.SWITCH and dev.key.device_type == DeviceType.GASVALVE:
            async_add_entities([NavienSwitch(gateway, dev)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_device)
    )

class NavienSwitch(SwitchEntity):
    """OFF means closed; remote opening is not supported."""

    _attr_should_poll = False

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        self._attr_name = "가스 밸브 (OFF=닫힘)"
        self._attr_icon = "mdi:gas-cylinder"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_update_{self._device.key.unique_id}", self._update)
        )

    @callback
    def _update(self, state):
        self._device = state
        self.async_write_ha_state()

    @property
    def is_on(self):
        closed = self._device.state
        return None if closed is None else not closed

    @property
    def extra_state_attributes(self):
        closed = self._device.state
        return {"valve_state": "unknown" if closed is None else "closed" if closed else "open",
                "state_meaning": "OFF=닫힘, ON=열림", "remote_open_supported": False}

    async def async_turn_on(self, **kwargs):
        raise HomeAssistantError("가스 원격 열림은 검증되지 않아 지원하지 않습니다. OFF는 차단입니다.")

    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
