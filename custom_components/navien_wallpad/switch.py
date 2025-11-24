from __future__ import annotations
from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN
from .models import DeviceType

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_switch(dev):
        if dev.platform == Platform.SWITCH:
            async_add_entities([NavienSwitch(gateway, dev, entry.entry_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_switch)
    )

class NavienSwitch(SwitchEntity):
    def __init__(self, gateway, device, entry_id):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = f"{device.key.unique_id}_{entry_id}"
        self._attr_name = "Gas" if device.key.device_type == DeviceType.GASVALVE else "Elevator"
        self._attr_icon = "mdi:gas-cylinder" if device.key.device_type == DeviceType.GASVALVE else "mdi:elevator"

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
        self._attr_is_on = state.state
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self.gateway.send(self._device.key, "on")

    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
