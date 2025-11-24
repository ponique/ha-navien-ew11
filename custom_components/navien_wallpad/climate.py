from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform  # ★ 필수
from .const import DOMAIN

# ★ 이름 설정 (여기서 수정하세요)
NAME_MAP = {
    1: "거실 난방",
    2: "안방 난방",
    3: "방1 난방",
    4: "방2 난방"
}

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_device(dev):
        # ★ [수정됨] 상수 사용
        if dev.platform == Platform.CLIMATE:
            async_add_entities([NavienClimate(gateway, dev)])

class NavienClimate(ClimateEntity):
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = ["none", "away"]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    _attr_temperature_unit = "°C"
    _attr_min_temp = 10
    _attr_max_temp = 40

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        
        # 이름 매핑 적용
        idx = device.key.index
        self._attr_name = NAME_MAP.get(idx, f"Heating {idx}")

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_update_{self._device.key.unique_id}", self._update)
        )

    def _update(self, state):
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
