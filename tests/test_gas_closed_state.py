"""Offline controller regressions; no HA server or physical commands are used."""
import ast
from enum import Enum
import logging
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Platform:
    LIGHT = "light"
    CLIMATE = "climate"
    FAN = "fan"
    SWITCH = "switch"


class HVACMode(str, Enum):
    HEAT = "heat"
    OFF = "off"


def load_controller():
    """Execute actual source with only HA imports replaced by offline constants."""
    import sys
    import types
    package = types.ModuleType("ew11_offline_models")
    package.__dict__["Platform"] = Platform
    sys.modules[package.__name__] = package
    model_path = ROOT / "custom_components/navien_wallpad/models.py"
    tree = ast.parse(model_path.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module == "homeassistant.const"
    )]
    exec(compile(tree, str(model_path), "exec"), package.__dict__)
    namespace = dict(package.__dict__, logging=logging, PACKET_PREFIX=0xF7,
                     HVACMode=HVACMode)
    path = ROOT / "custom_components/navien_wallpad/controller.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body
                 if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace["NavienController"], package.DeviceType


Controller, DeviceType = load_controller()


class Gateway:
    def __init__(self):
        self.updates = []

    def update_device(self, state):
        self.updates.append(state)


def frame(device, sub, command, payload):
    body = bytes([0xF7, device, sub, command, len(payload)]) + payload
    xor = 0
    for byte in body:
        xor ^= byte
    body += bytes([xor])
    return body + bytes([sum(body) & 0xFF])


class GasClosedStateTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway()
        self.controller = Controller(self.gateway)

    def states(self):
        return [update.state for update in self.gateway.updates]

    def test_open_report_then_observed_closure(self):
        self.controller.feed(bytes.fromhex("f712018102000166f4"))
        self.controller.feed(bytes.fromhex("f712018102000265f4"))
        self.assertEqual(self.states(), [False, True])
        self.assertEqual(self.gateway.updates[-1].key.unique_id, "gasvalve_1")
        self.assertEqual(self.gateway.updates[-1].platform, Platform.SWITCH)

    def test_fragmented_closure_followed_by_legacy_closed_report(self):
        closed = bytes.fromhex("f712018102000265f4")
        self.controller.feed(closed[:6])
        self.assertEqual(self.states(), [])
        self.controller.feed(closed[6:] + bytes.fromhex("f712018102000463f4"))
        self.assertEqual(self.states(), [True, True])

    def test_short_status_payload_does_not_update(self):
        self.controller.feed(frame(0x12, 1, 0x81, b"\x00"))
        self.assertEqual(self.states(), [])

    def test_bad_checksum_does_not_report_closed(self):
        packet = bytearray(bytes.fromhex("f712018102000265f4"))
        packet[-1] ^= 1
        self.controller.feed(packet)
        self.assertEqual(self.states(), [])

    def test_command_bytes_are_unchanged_and_match_observed_closure(self):
        # Generate bytes only; there is no transport or physical transmission.
        expected = bytes.fromhex("f71201410100a4f0")
        self.assertEqual(self.controller.make_cmd(DeviceType.GASVALVE, 1, "on"), expected)
        self.assertEqual(self.controller.make_cmd(DeviceType.GASVALVE, 1, "off"), expected)

    def test_thermostat_temperature_and_away_mapping_unchanged(self):
        payload = bytes([0, 0x0E, 1, 0, 0, 20, 25, 21, 26])
        self.controller.feed(frame(0x36, 0x1F, 0x81, payload))
        first, second = self.states()
        self.assertEqual(first, {"hvac_mode": HVACMode.OFF, "preset_mode": "away",
                                 "current_temp": 25.0, "target_temp": 20.0})
        self.assertEqual(second, {"hvac_mode": HVACMode.HEAT, "preset_mode": "none",
                                  "current_temp": 26.0, "target_temp": 21.0})


if __name__ == "__main__":
    unittest.main()
