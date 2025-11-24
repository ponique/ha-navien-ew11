from __future__ import annotations
from homeassistant.const import Platform

DOMAIN = "navien_wallpad"
PLATFORMS = [
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SWITCH,
]

CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 8888

PACKET_PREFIX = b'\xF7'