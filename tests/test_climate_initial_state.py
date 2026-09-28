"""Offline initial-registration regression; no physical commands are sent."""
import ast
import asyncio
from enum import Enum, IntFlag
from pathlib import Path
from types import SimpleNamespace
import unittest


class HVACMode(str, Enum):
    OFF = "off"
    HEAT = "heat"


class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    PRESET_MODE = 2
    TURN_ON = 4
    TURN_OFF = 8


class ClimateEntity:
    # Initial HA registration reads these before any subsequent packet update.
    @property
    def hvac_mode(self):
        return self._attr_hvac_mode

    @property
    def preset_mode(self):
        return self._attr_preset_mode

    @property
    def current_temperature(self):
        return self._attr_current_temperature

    @property
    def target_temperature(self):
        return self._attr_target_temperature

    def async_write_ha_state(self):
        self.writes = getattr(self, "writes", 0) + 1


path = Path(__file__).resolve().parents[1] / "custom_components/navien_wallpad/climate.py"
tree = ast.parse(path.read_text(encoding="utf-8"))
tree.body = [node for node in tree.body
             if not isinstance(node, (ast.Import, ast.ImportFrom))]
namespace = dict(ClimateEntity=ClimateEntity, ClimateEntityFeature=ClimateEntityFeature,
                 HVACMode=HVACMode, callback=lambda fn: fn, DOMAIN="navien_wallpad")
exec(compile(tree, str(path), "exec"), namespace)
NavienClimate = namespace["NavienClimate"]


def device(mode=HVACMode.HEAT, preset="none", current=25.0, target=20.0):
    return SimpleNamespace(
        key=SimpleNamespace(index=1, unique_id="thermostat_1"),
        state=dict(hvac_mode=mode, preset_mode=preset,
                   current_temp=current, target_temp=target))


class Gateway:
    def __init__(self):
        self.requests = []

    async def send(self, key, action, **kwargs):
        self.requests.append((key.unique_id, action, kwargs))


class ClimateInitialStateTests(unittest.TestCase):
    def test_initial_registration_reads_heating_without_waiting_for_next_packet(self):
        entity = NavienClimate(Gateway(), device())
        self.assertEqual((entity.hvac_mode, entity.preset_mode,
                          entity.current_temperature, entity.target_temperature),
                         (HVACMode.HEAT, "none", 25.0, 20.0))
        self.assertEqual(getattr(entity, "writes", 0), 0)

    def test_initial_registration_preserves_away_state(self):
        entity = NavienClimate(Gateway(), device(HVACMode.OFF, "away", 24.0, 18.0))
        self.assertEqual((entity.hvac_mode, entity.preset_mode,
                          entity.current_temperature, entity.target_temperature),
                         (HVACMode.OFF, "away", 24.0, 18.0))

    def test_subsequent_update_replaces_all_fields_and_writes_once(self):
        entity = NavienClimate(Gateway(), device())
        replacement = device(HVACMode.OFF, "away", 24.5, 18.5)
        entity._update(replacement)
        self.assertIs(entity._device, replacement)
        self.assertEqual((entity.hvac_mode, entity.preset_mode,
                          entity.current_temperature, entity.target_temperature),
                         (HVACMode.OFF, "away", 24.5, 18.5))
        self.assertEqual(entity.writes, 1)

    def test_identifiers_and_gateway_requests_are_unchanged(self):
        gateway = Gateway()
        entity = NavienClimate(gateway, device())
        self.assertEqual(entity._attr_unique_id, "thermostat_1")
        self.assertEqual(entity._attr_name, "거실 난방")
        asyncio.run(entity.async_set_temperature(temperature=21))
        asyncio.run(entity.async_set_hvac_mode(HVACMode.HEAT))
        asyncio.run(entity.async_set_preset_mode("away"))
        self.assertEqual(gateway.requests, [
            ("thermostat_1", "temp", {"temp": 21}),
            ("thermostat_1", "hvac", {"mode": HVACMode.HEAT}),
            ("thermostat_1", "away", {"mode": "away"}),
        ])


if __name__ == "__main__":
    unittest.main()
