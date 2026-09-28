"""Offline behavior tests using actual source; no sockets or device actions."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from test_gas_closed_state import Controller, DeviceType, Platform, Gateway, frame

ROOT = Path(__file__).resolve().parents[1]


class HomeAssistantError(Exception):
    pass


class Entity:
    def async_write_ha_state(self):
        self.writes = getattr(self, 'writes', 0) + 1


def load(name):
    path = ROOT / 'custom_components/navien_wallpad' / (name + '.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ns = dict(SwitchEntity=Entity, ButtonEntity=Entity, DeviceType=DeviceType,
              Platform=Platform, callback=lambda f:f, DOMAIN='navien_wallpad',
              HomeAssistantError=HomeAssistantError)
    exec(compile(tree, str(path), 'exec'), ns)
    return ns


Switch = load('switch')['NavienSwitch']
Button = load('button')['NavienElevatorButton']


class Sender:
    def __init__(self): self.calls=[]
    async def send(self, key, action, **kw): self.calls.append((key.unique_id, action, kw))


def device(closed, dtype=DeviceType.GASVALVE):
    return SimpleNamespace(state=closed, key=SimpleNamespace(
        device_type=dtype, unique_id='gasvalve_1' if dtype==DeviceType.GASVALVE else 'elevator_1'))


class EntitySemanticsTests(unittest.TestCase):
    def test_gas_initial_closed_is_off_open_is_on_unknown_is_unknown(self):
        for closed, expected in ((True, False),(False,True),(None,None)):
            entity=Switch(Sender(),device(closed))
            self.assertIs(entity.is_on,expected)
            self.assertFalse(entity.extra_state_attributes['remote_open_supported'])

    def test_gas_update_closed_is_off_with_explicit_attribute(self):
        entity=Switch(Sender(),device(False));entity._update(device(True))
        self.assertFalse(entity.is_on)
        self.assertEqual(entity.extra_state_attributes['valve_state'],'closed')
        self.assertEqual(entity.writes,1)

    def test_open_request_errors_without_sending_or_changing_state(self):
        sender=Sender();entity=Switch(sender,device(True))
        with self.assertRaises(HomeAssistantError):asyncio.run(entity.async_turn_on())
        self.assertEqual(sender.calls,[]);self.assertFalse(entity.is_on)

    def test_close_request_uses_off_and_waits_for_received_feedback(self):
        sender=Sender();entity=Switch(sender,device(False))
        asyncio.run(entity.async_turn_off())
        self.assertEqual(sender.calls,[('gasvalve_1','off',{})])
        self.assertTrue(entity.is_on)

    def test_unknown_gas_code_does_not_claim_open_or_closed(self):
        gateway=Gateway();Controller(gateway).feed(frame(0x12,1,0x81,b'\x00\x07'))
        self.assertIsNone(gateway.updates[-1].state)

    def test_elevator_status_selects_button_platform(self):
        gateway=Gateway();Controller(gateway).feed(frame(0x33,1,0x81,b'\x00\x44\x00'))
        self.assertEqual(gateway.updates[-1].platform,Platform.BUTTON)

    def test_repeated_presses_each_send_even_when_periodic_status_is_true(self):
        sender=Sender();button=Button(sender,device(True,DeviceType.ELEVATOR))
        asyncio.run(button.async_press());asyncio.run(button.async_press())
        self.assertEqual(sender.calls,[('elevator_1','call',{}),('elevator_1','call',{})])
        self.assertFalse(button._attr_should_poll)

    def test_elevator_command_bytes_preserved_and_switch_actions_rejected(self):
        controller=Controller(Gateway())
        self.assertEqual(controller.make_cmd(DeviceType.ELEVATOR,1,'call'),bytes.fromhex('f733014301109716'))
        for action in ('on','off'):
            with self.assertRaises(ValueError):controller.make_cmd(DeviceType.ELEVATOR,1,action)

    def test_platform_setup_creates_only_matching_device(self):
        for module, expected in (('button',Platform.BUTTON),('switch',Platform.SWITCH)):
            ns=load(module);listeners=[];added=[]
            ns['async_dispatcher_connect']=lambda hass,signal,fn:listeners.append(fn)
            entry=SimpleNamespace(entry_id='test',async_on_unload=lambda fn:None)
            hass=SimpleNamespace(data={'navien_wallpad':{'test':Sender()}})
            asyncio.run(ns['async_setup_entry'](hass,entry,lambda entities:added.extend(entities)))
            elevator=device(True,DeviceType.ELEVATOR);elevator.platform=Platform.BUTTON
            gas=device(True);gas.platform=Platform.SWITCH
            for dev in (elevator,gas):listeners[0](dev)
            self.assertEqual(len(added),1)
            self.assertEqual(added[0]._device.platform,expected)


if __name__=='__main__':unittest.main()


