from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Union
from homeassistant.const import Platform

class DeviceType(IntEnum):
    LIGHT = 0x0E
    THERMOSTAT = 0x36
    VENTILATION = 0x32
    GASVALVE = 0x12
    ELEVATOR = 0x33
    UNKNOWN = 0x00

@dataclass(frozen=True)
class DeviceKey:
    device_type: DeviceType
    index: int

    @property
    def unique_id(self) -> str:
        return f"{self.device_type.name.lower()}_{self.index}"

@dataclass
class DeviceState:
    key: DeviceKey
    platform: Platform
    state: Any  # Fixed: any -> Any
    attributes: dict[str, Any] | None = None