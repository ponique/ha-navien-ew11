from __future__ import annotations
from homeassistant.core import callback
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_climate(dev):
        if dev.platform == Platform.CLIMATE:
            async_add_entities([NavienClimate(gateway, dev, entry.entry_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_climate)
    )

class NavienClimate(ClimateEntity):
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = ["none", "away"]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    _attr_temperature_unit = "°C"
    _attr_min_temp = 10
    _attr_max_temp = 40

    def __init__(self, gateway, device, entry_id):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = f"{device.key.unique_id}_{entry_id}"
        self._attr_name = f"Heating {device.key.index}"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, 
                f"{DOMAIN}_update_{self._device.key.unique_id}", 
                self._update_state
            )
        )

    @callback
    def _update_state(self, state):
        self._device = state
        self._attr_hvac_mode = state.state["hvac_mode"]
        self._attr_preset_mode = state.state["preset_mode"]
        self._attr_current_temperature = state.state["current_temp"]
        self._attr_target_temperature = state.state["target_temp"]
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        await self.gateway.send(self._device.key, "hvac", mode=hvac_mode)

    async def async_set_temperature(self, **kwargs):
        await self.gateway.send(self._device.key, "temp", temp=kwargs['temperature'])

    async def async_set_preset_mode(self, preset_mode):
        await self.gateway.send(self._device.key, "away", mode=preset_mode)
