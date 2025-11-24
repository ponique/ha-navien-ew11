from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN
from .models import DeviceType

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_device(dev):
        if dev.platform == "switch":
            async_add_entities([NavienSwitch(gateway, dev.key)])

class NavienSwitch(SwitchEntity):
    def __init__(self, gateway, key):
        self.gateway = gateway
        self._key = key
        self._attr_unique_id = key.unique_id
        self._attr_name = "Gas" if key.device_type == DeviceType.GASVALVE else "Elevator"
        self._attr_icon = "mdi:gas-cylinder" if key.device_type == DeviceType.GASVALVE else "mdi:elevator"
    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{DOMAIN}_update_{self._key.unique_id}", self._update))
    def _update(self, state):
        self._attr_is_on = state.state
        self.async_write_ha_state()
    async def async_turn_on(self, **kwargs): await self.gateway.send(self._key, "on")
    async def async_turn_off(self, **kwargs): await self.gateway.send(self._key, "off")