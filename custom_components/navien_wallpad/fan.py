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
    # 프리셋 목록
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
        self._attr_percentage = state.state["percentage"]
        self._attr_preset_mode = state.state["preset_mode"]
        self.async_write_ha_state()

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if preset_mode: 
            await self.async_set_preset_mode(preset_mode)
        elif percentage: 
            await self.async_set_percentage(percentage)
        else: 
            # ★ [수정됨] 그냥 켜면 'Low(약)' 모드로 시작 (Auto 방지)
            # 만약 Medium으로 켜고 싶으시면 "medium"으로 바꾸시면 됩니다.
            await self.async_set_preset_mode("low")
    
    async def async_turn_off(self, **kwargs):
        await self.gateway.send(self._device.key, "off")
    
    async def async_set_percentage(self, percentage):
        if percentage == 0:
            await self.async_turn_off()
        else:
            await self.gateway.send(self._device.key, "set_speed", pct=percentage)
        
    async def async_set_preset_mode(self, preset_mode):
        if preset_mode == "auto":
            await self.gateway.send(self._device.key, "on") # Auto Command (41 01 01)
        else:
            pct = 33
            if preset_mode == "medium": pct = 66
            elif preset_mode == "high": pct = 100
            
            # 해당 풍량 명령 전송 (42 01 XX)
            # 보통 꺼져있을 때 풍량 명령을 보내면 켜지면서 해당 풍량이 됩니다.
            await self.gateway.send(self._device.key, "set_speed", pct=pct)
