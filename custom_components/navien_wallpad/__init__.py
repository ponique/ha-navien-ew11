from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, CONF_HOST, CONF_PORT
from .gateway import NavienGateway

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    gateway = NavienGateway(hass, entry.data[CONF_HOST], entry.data[CONF_PORT])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = gateway
    await gateway.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # [수정됨] 플랫폼 언로드 먼저 시도
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # 성공 시 리소스 정리 및 데이터 삭제
    if unload_ok:
        gateway = hass.data[DOMAIN].pop(entry.entry_id)
        await gateway.stop()
        
    return unload_ok
