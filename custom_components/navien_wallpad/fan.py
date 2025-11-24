from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_device(dev):
        if dev.platform == "fan":
            async_add_entities([NavienFan(gateway, dev.key)])

class NavienFan(FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    def __init__(self, gateway, key):
        self.gateway = gateway
        self._key = key
        self._attr_unique_id = key.unique_id
        self._attr_name = "Ventilation"
    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{DOMAIN}_update_{self._key.unique_id}", self._update))
    def _update(self, state):
        self._attr_is_on = state.state["state"]
        self._attr_percentage = state.state["percentage"]
        self.async_write_ha_state()
    async def async_turn_on(self, percentage=None, **kwargs):
        if percentage: await self.async_set_percentage(percentage)
        else: await self.gateway.send(self._key, "on")
    async def async_turn_off(self, **kwargs): await self.gateway.send(self._key, "off")
    async def async_set_percentage(self, percentage): await self.gateway.send(self._key, "set_speed", pct=percentage)