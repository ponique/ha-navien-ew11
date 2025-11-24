from __future__ import annotations
from homeassistant.core import callback
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import Platform
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    gateway = hass.data[DOMAIN][entry.entry_id]
    
    @callback
    def add_fan(dev):
        if dev.platform == Platform.FAN:
            async_add_entities([NavienFan(gateway, dev, entry.entry_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, f"{DOMAIN}_new_device", add_fan)
    )

class NavienFan(FanEntity):
    # 속도 조절 + 켜기/끄기 + 프리셋(단계) 모드 지원
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED 
        | FanEntityFeature.TURN_ON 
        | FanEntityFeature.TURN_OFF 
        | FanEntityFeature.PRESET_MODE
    )
    
    # 1단계(Low), 2단계(Medium), 3단계(High) 정의
    _attr_preset_modes = ["low", "medium", "high"]

    def __init__(self, gateway, device, entry_id):
        self.gateway = gateway
        self._device = device
        self._attr_unique_id = f"{device.key.unique_id}_{entry_id}"
        self._attr_name = "Ventilation"

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
        self._attr_is_on = state.state["state"]
        self._attr_percentage = state.state["percentage"]
        self._attr_preset_mode = state.state["preset_mode"] # 현재 프리셋 상태 반영
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage: 
            await self.async_set_percentage(percentage)
        else: 
            await self.gateway.send(self._device.key, "on")

    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")

    async def async_set_percentage(self, percentage):
        # 슬라이더 조작 시
        await self.gateway.send(self._device.key, "set_speed", pct=percentage)

    async def async_set_preset_mode(self, preset_mode):
        # 버튼(약/중/강) 조작 시 -> 해당 퍼센트로 변환해서 전송
        pct = 33
        if preset_mode == "medium": pct = 66
        elif preset_mode == "high": pct = 100
        
        await self.gateway.send(self._device.key, "set_speed", pct=pct)
