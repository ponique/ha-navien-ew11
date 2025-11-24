from homeassistant.core import callback
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN

# ★ 이름 고정
NAME_MAP = {
    1: "거실등1",
    2: "거실등2",
    3: "복도등"
}

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_light(dev):
        if dev.platform == Platform.LIGHT:
            async_add_entities([NavienLight(gateway, dev)])

    # ★ 일반 함수 호출로 변경 (에러 해결됨)
    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_light)
    )

class NavienLight(LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        
        # 이름 적용
        idx = device.key.index
        self._attr_name = NAME_MAP.get(idx, f"Light {idx}")

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
