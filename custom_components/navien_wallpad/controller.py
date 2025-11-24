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

            valid = False
            for l in range(7, min(len(self._rx_buf)+1, 60)):
                candidate = self._rx_buf[:l]
                if self._check_integrity(candidate):
                    self._parse(candidate)
                    del self._rx_buf[:l]
                    valid = True
                    break
            
            if not valid:
                if len(self._rx_buf) > 60: del self._rx_buf[0]
                else: break

    def _check_integrity(self, pkt):
        if len(pkt) < 7: return False
        xor = 0
        add = 0
        for b in pkt[:-2]: xor ^= b
        if xor != pkt[-2]: return False
        for b in pkt[:-1]: add += b
        if (add & 0xFF) != pkt[-1]: return False
        return True

    def _parse_temp(self, raw_val):
        temp = float(raw_val & 0x7F)
        if raw_val & 0x80: temp += 0.5
        return temp

    def _parse(self, pkt):
        dev_id = pkt[1]
        cmd = pkt[3]
        
        try:
            data_len = pkt[4]
            if len(pkt) < 5 + data_len + 2: return
            data = pkt[5:5+data_len]
        except IndexError: return

        # 1. Light (0x0E)
        if dev_id == 0x0E and cmd == 0x81:
            if len(data) >= 2: 
                for i, val in enumerate(data[1:]):
                    self._update(DeviceType.LIGHT, i+1, val == 0x01)

        # 2. Thermostat (0x36) - ★ [완벽 복구: 짝지어 읽기]
        elif dev_id == 0x36 and cmd == 0x81:
            if len(data) >= 5:
                pwr_mask = data[1]
                away_mask = data[2]
                
                temp_data = data[5:]
                room_count = len(temp_data) // 2
                
                for i in range(room_count):
                    is_on = bool(pwr_mask & (1 << i))
                    is_away = bool(away_mask & (1 << i))
                    
                    # [복구] 짝수 인덱스: 설정온도, 홀수 인덱스: 현재온도 (Interleaved)
                    s_temp = self._parse_temp(temp_data[i*2])
                    c_temp = self._parse_temp(temp_data[i*2+1])
                    
                    if c_temp == 0 and s_temp == 0: continue

                    state = {
                        "hvac_mode": HVACMode.HEAT if is_on else HVACMode.OFF,
                        "preset_mode": "away" if is_away else "none",
                        "current_temp": c_temp,
                        "target_temp": s_temp
                    }
                    self._update(DeviceType.THERMOSTAT, i+1, state)

        # 3. Fan (0x32) - [유지]
        elif dev_id == 0x32 and cmd == 0x81:
            if len(data) >= 3:
                pwr_byte = data[1]
                mode_byte = data[2]
                
                is_on = (pwr_byte != 0x00)
                pct = 0
                preset = None 
                
                if is_on:
                    if mode_byte == 0x02 or speed_byte == 0x04: 
                        preset = "auto"
                        pct = 50 
                    elif mode_byte == 0x03: 
                        preset = "high"
                        pct = 100
                    else: 
                        preset = "low" 
                        pct = 33
                
                state = {"state": is_on, "percentage": pct, "preset_mode": preset}
                self._update(DeviceType.VENTILATION, 1, state)

        # 4. Gas (0x12)
        elif dev_id == 0x12 and cmd == 0x81:
            if len(data) >= 2:
                is_closed = (data[1] == 0x04)
                self._update(DeviceType.GASVALVE, 1, is_closed)

        # 5. Elevator (0x33)
        elif dev_id == 0x33 and cmd == 0x81:
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
                target = float(kwargs['temp'])
                int_part = int(target)
                val = int_part
                if (target - int_part) >= 0.5: val |= 0x80
                payload = [0x01, val]
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
                elif pct > 33: val = 0x02
                elif pct == 50: val = 0x04 # Auto
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
