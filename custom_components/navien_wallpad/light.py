from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_light(dev):
        if dev.platform == "light":
            async_add_entities([NavienLight(gateway, dev, entry.entry_id)])

class NavienLight(LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, gateway, device, entry_id):
        self.gateway = gateway
        self._device = device
        # Unique ID: navien_light_1_ENTRYID (절대 안 겹침)
        self._attr_unique_id = f"{device.key.unique_id}_{entry_id}"
        self._attr_name = f"Light {device.key.index}"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, 
                f"{DOMAIN}_update_{self._device.key.unique_id}", 
                self._update_state
            )
        )

    def _update_state(self, state):
        self._device = state
        self._attr_is_on = state.state
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self.gateway.send(self._device.key, "on")

    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")