from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform  # ★ 필수
from .const import DOMAIN

# ★ 이름 설정 (여기서 수정하세요)
NAME_MAP = {
    1: "거실등1",
    2: "거실등2",
    3: "복도등"
}

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_light(dev):
        # ★ [수정됨] 문자열 "light"가 아니라 상수 Platform.LIGHT 사용
        if dev.platform == Platform.LIGHT:
            async_add_entities([NavienLight(gateway, dev)])

class NavienLight(LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        
        # 이름 매핑 적용
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

    def _update_state(self, state):
        self._device = state
        self._attr_is_on = state.state
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self.gateway.send(self._device.key, "on")

    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
