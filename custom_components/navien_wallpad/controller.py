import logging
from .const import PACKET_PREFIX
from .models import DeviceType, DeviceKey, DeviceState
from homeassistant.const import Platform
from homeassistant.components.climate.const import HVACMode

LOGGER = logging.getLogger(__name__)

class NavienController:
    def __init__(self, gateway):
        self.gateway = gateway
        self._rx_buf = bytearray()

    def feed(self, data: bytes):
        self._rx_buf.extend(data)
        while True:
            try:
                start = self._rx_buf.index(PACKET_PREFIX)
                if start > 0: del self._rx_buf[:start]
            except ValueError:
                self._rx_buf.clear()
                break

            if len(self._rx_buf) < 7: break

            packet_found = False
            # Max packet length safe guard
            for l in range(7, min(len(self._rx_buf)+1, 60)):
                candidate = self._rx_buf[:l]
                if self._check_integrity(candidate):
                    self._parse(candidate)
                    del self._rx_buf[:l]
                    packet_found = True
                    break
            
            if not packet_found:
                if len(self._rx_buf) > 60: del self._rx_buf[0]
                else: break

    def _check_integrity(self, pkt):
        xor = 0
        add = 0
        for b in pkt[:-2]: xor ^= b
        for b in pkt[:-1]: add += b
        return xor == pkt[-2] and (add & 0xFF) == pkt[-1]

    def _parse(self, pkt):
        dev_id = pkt[1]
        cmd = pkt[3]
        # Data payload (exclude Header/ID/Sub/Cmd/Len ... XOR/ADD)
        # However, length byte is at pkt[4].
        try:
            d_len = pkt[4]
            if len(pkt) < 5 + d_len + 2: return # Safety check
            data = pkt[5:5+d_len]
        except IndexError: return

        # 1. Light (0x0E)
        if dev_id == 0x0E and cmd == 0x81:
            # Log: 04 00 [L1] [L2] ...
            if len(data) >= 2 and data[0] == 0x04:
                # data[1] is 00
                for i, val in enumerate(data[2:]):
                    self._update(DeviceType.LIGHT, i+1, val == 0x01)

        # 2. Thermostat (0x36)
        elif dev_id == 0x36 and cmd == 0x81:
            # Log: 0D 00 01 0E 00 00 [Cur:17..] [Set:16..]
            # Indices: 0=0D, 1=00, 2=01(Pwr), 3=0E(Away), 4=00, 5=00
            # CurTemp starts at 6, SetTemp starts at 11
            # But 'data' variable excludes 'LEN'(0D).
            # So data[0]=00, data[1]=Pwr, data[2]=Away, data[3]=00, data[4]=00
            # CurTemp starts at data[5]
            # SetTemp starts at data[10]
            
            if len(data) >= 15:
                pwr_mask = data[1]
                away_mask = data[2]
                cur_temps = data[5:10]  # 5 bytes
                set_temps = data[10:15] # 5 bytes
                
                for i in range(5):
                    # Room index bit check
                    is_on = bool(pwr_mask & (1 << i))
                    is_away = bool(away_mask & (1 << i))
                    
                    # Invalid temp check (0 degree is unlikely)
                    c_temp = int(cur_temps[i])
                    s_temp = int(set_temps[i])
                    if c_temp == 0 and s_temp == 0: continue

                    state = {
                        "hvac_mode": HVACMode.HEAT if is_on else HVACMode.OFF,
                        "preset_mode": "away" if is_away else "none",
                        "current_temp": c_temp,
                        "target_temp": s_temp
                    }
                    self._update(DeviceType.THERMOSTAT, i+1, state)

        # 3. Fan (0x32)
        elif dev_id == 0x32 and cmd == 0x81:
            # Log: 05 00 [Pwr] [Mode] [Speed]
            # data[0]=00, data[1]=Pwr, data[2]=Mode
            if len(data) >= 3:
                is_on = data[1] != 0x00
                mode = data[2]
                
                pct = 0
                if is_on:
                    if mode == 0x01: pct = 33
                    elif mode == 0x02: pct = 66
                    elif mode == 0x03: pct = 100
                
                state = {"state": is_on, "percentage": pct}
                self._update(DeviceType.VENTILATION, 1, state)

        # 4. Gas (0x12)
        elif dev_id == 0x12 and cmd == 0x81:
            # Log: 02 00 [State] -> data[0]=00, data[1]=State
            if len(data) >= 2:
                is_closed = (data[1] == 0x04)
                self._update(DeviceType.GASVALVE, 1, is_closed)

        # 5. Elevator (0x33)
        elif dev_id == 0x33 and cmd == 0x81:
            # Log: 03 00 [State] -> data[0]=00, data[1]=State
            if len(data) >= 2:
                is_active = (data[1] == 0x44)
                self._update(DeviceType.ELEVATOR, 1, is_active)

    def _update(self, dtype, idx, state):
        key = DeviceKey(dtype, idx)
        plat = {
            DeviceType.LIGHT: Platform.LIGHT,
            DeviceType.THERMOSTAT: Platform.CLIMATE,
            DeviceType.VENTILATION: Platform.FAN,
            DeviceType.GASVALVE: Platform.SWITCH,
            DeviceType.ELEVATOR: Platform.SWITCH
        }.get(dtype)
        
        if plat:
            self.gateway.update_device(DeviceState(key, plat, state))

    def make_cmd(self, dtype, idx, action, **kwargs):
        did = dtype.value
        sub = 0x01
        cmd = 0x41
        payload = []

        if dtype == DeviceType.LIGHT:
            sub = 0x10 + idx
            val = 0x01 if action == "on" else 0x00
            payload = [0x01, val]

        elif dtype == DeviceType.THERMOSTAT:
            sub = 0x10 + idx
            if action == "hvac":
                cmd = 0x43
                val = 0x01 if kwargs['mode'] == HVACMode.HEAT else 0x00
                payload = [0x01, val]
            elif action == "temp":
                cmd = 0x44
                payload = [0x01, int(kwargs['temp'])]
            elif action == "away":
                cmd = 0x45
                val = 0x01 if kwargs['mode'] == "away" else 0x00
                payload = [0x01, val]

        elif dtype == DeviceType.VENTILATION:
            if action == "set_speed":
                cmd = 0x42
                pct = kwargs['pct']
                val = 0x01
                if pct > 66: val = 0x03
                elif pct > 33: val = 0x02 # 02 is Auto/Mid based on logs
                payload = [0x01, val]
            else:
                cmd = 0x41
                val = 0x01 if action == "on" else 0x00
                payload = [0x01, val]

        elif dtype == DeviceType.GASVALVE:
            cmd = 0x41
            payload = [0x01, 0x00]

        elif dtype == DeviceType.ELEVATOR:
            cmd = 0x43
            payload = [0x01, 0x10]

        base = [0xF7, did, sub, cmd] + payload
        xor = 0
        for b in base: xor ^= b
        add = 0
        for b in base: add += b
        add += xor 
        
        return bytes(base + [xor, add & 0xFF])