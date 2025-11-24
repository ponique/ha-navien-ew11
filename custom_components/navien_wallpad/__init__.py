from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, CONF_HOST, CONF_PORT
from .gateway import NavienGateway

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    gateway = NavienGateway(hass, entry.data[CONF_HOST], entry.data[CONF_PORT])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = gateway
    
    # 1. 기기 등록(Platform) 먼저 실행 (리스너 등록)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 2. 통신 시작 (패킷 수신)
    await gateway.start()
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        gateway = hass.data[DOMAIN].pop(entry.entry_id)
        await gateway.stop()
    return unload_ok
