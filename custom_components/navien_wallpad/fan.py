from homeassistant.core import callback
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_device(dev):
        if dev.platform == Platform.FAN:
            async_add_entities([NavienFan(gateway, dev)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_device)
    )

class NavienFan(FanEntity):
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED 
        | FanEntityFeature.TURN_ON 
        | FanEntityFeature.TURN_OFF 
        | FanEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = ["auto", "low", "medium", "high"]
    _attr_speed_count = 3

    def __init__(self, gateway, device):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = device.key.unique_id
        self._attr_name = "전열교환기"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_update_{self._device.key.unique_id}", self._update_state
            )
        )

    @callback
    def _update_state(self, state):
        self._device = state
        self._attr_is_on = state.state["state"]
        
        # 켜져있을 때만 값 반영, 꺼져있으면 None/0 처리
        if self._attr_is_on:
            self._attr_percentage = state.state["percentage"]
            self._attr_preset_mode = state.state["preset_mode"]
        else:
            self._attr_percentage = 0
            self._attr_preset_mode = None
            
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if preset_mode: 
            await self.async_set_preset_mode(preset_mode)
        elif percentage: 
            await self.async_set_percentage(percentage)
        else: 
            # ★ 그냥 켜기 -> Auto 모드로 켜기 시도 (가장 확실함)
            await self.async_set_preset_mode("auto")
    
    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
    
    async def async_set_percentage(self, percentage):
        if percentage == 0:
            await self.async_turn_off()
        else:
            # 꺼져있으면 켜기 (Auto) 후 속도 변경
            if not self.is_on:
                await self.gateway.send(self._device.key, "on")
            
            await self.gateway.send(self._device.key, "set_speed", pct=percentage)
        
    async def async_set_preset_mode(self, preset_mode):
        pct = 33
        if preset_mode == "auto": 
            pct = 50
        elif preset_mode == "medium": 
            pct = 66
        elif preset_mode == "high": 
            pct = 100
        
        await self.gateway.send(self._device.key, "set_speed", pct=pct)
