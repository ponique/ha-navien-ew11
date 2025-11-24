from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform  # ★ 필수
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    @async_dispatcher_connect(hass, f"{DOMAIN}_new_device")
    def add_device(dev):
        # ★ [수정됨] 상수 사용
        if dev.platform == Platform.FAN:
            async_add_entities([NavienFan(gateway, dev)])

class NavienFan(FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.PRESET_MODE
    _attr_preset_modes = ["low", "medium", "high"]

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        self._attr_name = "전열교환기" # 이름 고정

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{DOMAIN}_update_{self._device.key.unique_id}", self._update))

    def _update(self, state):
        self._device = state
        self._attr_is_on = state.state["state"]
        self._attr_percentage = state.state["percentage"]
        self._attr_preset_mode = state.state["preset_mode"]
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if preset_mode: await self.async_set_preset_mode(preset_mode)
        elif percentage: await self.async_set_percentage(percentage)
        else: await self.gateway.send(self._device.key, "on")
    
    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
    
    async def async_set_percentage(self, percentage):
        await self.gateway.send(self._device.key, "set_speed", pct=percentage)
        
    async def async_set_preset_mode(self, preset_mode):
        pct = 33
        if preset_mode == "medium": pct = 66
        elif preset_mode == "high": pct = 100
        await self.gateway.send(self._device.key, "set_speed", pct=pct)
