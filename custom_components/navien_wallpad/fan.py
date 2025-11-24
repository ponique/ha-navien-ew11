import asyncio
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
        
        if self._attr_is_on:
            self._attr_percentage = state.state["percentage"]
            self._attr_preset_mode = state.state["preset_mode"]
        else:
            self._attr_percentage = 0
            self._attr_preset_mode = None
            
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        # 켜기 버튼 (토글)만 눌렀을 경우 Auto 모드로 유도
        if not preset_mode and not percentage:
            await self.async_set_preset_mode("auto")
            return
            
        if preset_mode: 
            await self.async_set_preset_mode(preset_mode)
        elif percentage: 
            await self.async_set_percentage(percentage)
    
    async def async_turn_off(self, **kwargs):
        # OFF 명령 전송 후, UI를 OFF로 강제 업데이트 (바운스 방지)
        await self.gateway.send(self._device.key, "off")
        
        # Optimistic Update
        self._attr_is_on = False
        self._attr_percentage = 0
        self._attr_preset_mode = None
        self.async_write_ha_state()
    
    async def async_set_percentage(self, percentage):
        if percentage == 0:
            await self.async_turn_off()
            return
        
        # 1. Power ON + 딜레이
        if not self.is_on:
            await self.gateway.send(self._device.key, "on")
            await asyncio.sleep(1.0) # 1.0초 딜레이 (안정성 확보)

        # 2. 속도 설정
        await self.gateway.send(self._device.key, "set_speed", pct=percentage)
        
    async def async_set_preset_mode(self, preset_mode):
        # 1. Power ON + 딜레이
        if not self.is_on:
            await self.gateway.send(self._device.key, "on")
            await asyncio.sleep(1.0)

        pct = 33
        if preset_mode == "auto": pct = 50
        elif preset_mode == "medium": pct = 66
        elif preset_mode == "high": pct = 100
        
        await self.gateway.send(self._device.key, "set_speed", pct=pct)
