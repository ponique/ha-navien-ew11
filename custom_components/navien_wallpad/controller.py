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

            pkt_len = 0
            valid = False
            
            # 체크섬이 맞는 패킷 찾기
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
        # Checksum: XOR, ADD
        if len(pkt) < 7: return False
        xor = 0
        add = 0
        
        for b in pkt[:-2]: xor ^= b
        if xor != pkt[-2]: return False
        
        for b in pkt[:-1]: add += b
        if (add & 0xFF) != pkt[-1]: return False
        
        return True

    def _parse(self, pkt):
        dev_id = pkt[1]
        cmd = pkt[3]
        
        try:
            # pkt[4]는 데이터 길이(Len)
            data_len = pkt[4]
            # 실제 데이터는 인덱스 5부터 시작
            if len(pkt) < 5 + data_len + 2: return
            data = pkt[5:5+data_len]
        except IndexError: return

        # ==========================================
        # 1. Light (0x0E) - 조명 (수정됨)
        # ==========================================
        if dev_id == 0x0E and cmd == 0x81:
            # Log: F7 0E ... 04 [00] [01] [01] [01] ...
            # Len: 04
            # Data: 00(Dummy) 01(L1) 01(L2) 01(L3)
            
            # data[0]은 00이므로 무시하고, data[1]부터 읽어야 함
            if len(data) >= 2: 
                for i, val in enumerate(data[1:]):
                    # i=0 -> data[1] -> Light 1
                    # i=1 -> data[2] -> Light 2
                    self._update(DeviceType.LIGHT, i+1, val == 0x01)

        # ==========================================
        # 2. Thermostat (0x36) - 난방 (확인됨)
        # ==========================================
        elif dev_id == 0x36 and cmd == 0x81:
            # Log: 0D [00] [01] [0E] ...
            # Data: 00(Dummy) 01(Power) 0E(Away) ...
            if len(data) >= 10: 
                try:
                    pwr_mask = data[1] # Index 1 is Power
                    away_mask = data[2] # Index 2 is Away
                    cur_temps = data[5:10] # Index 5~9 is Current Temp
                    set_temps = data[10:]  # Index 10~ is Target Temp
                    
                    for i in range(5):
                        if i >= len(cur_temps): break
                        
                        is_on = bool(pwr_mask & (1 << i))
                        is_away = bool(away_mask & (1 << i))
                        c_temp = int(cur_temps[i])
                        s_temp = int(set_temps[i]) if i < len(set_temps) else 0
                        
                        if c_temp == 0 and s_temp == 0: continue

                        state = {
                            "hvac_mode": HVACMode.HEAT if is_on else HVACMode.OFF,
                            "preset_mode": "away" if is_away else "none",
                            "current_temp": c_temp,
                            "target_temp": s_temp
                        }
                        self._update(DeviceType.THERMOSTAT, i+1, state)
                except IndexError: pass

        # ==========================================
        # 3. Fan (0x32) - 환기
        # ==========================================
        elif dev_id == 0x32 and cmd == 0x81:
            # Log: 05 [00] [01] [03] (Pwr, Mode, Speed ? - 추정)
            # 사용자 로그: F7 32 ... 81 05 00 00 00 04 (OFF)
            # 사용자 로그: F7 32 ... 81 05 00 01 02 04 (ON, Auto)
            # Data[0]=00, Data[1]=Power, Data[2]=Mode
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

        # ==========================================
        # 4. Gas (0x12) - 가스
        # ==========================================
        elif dev_id == 0x12 and cmd == 0x81:
            # Log: 02 [00] [State]
            if len(data) >= 2:
                is_closed = (data[1] == 0x04) 
                self._update(DeviceType.GASVALVE, 1, is_closed)

        # ==========================================
        # 5. Elevator (0x33) - 엘리베이터
        # ==========================================
        elif dev_id == 0x33 and cmd == 0x81:
            # Log: 03 [00] [State]
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
                elif pct > 33: val = 0x02
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
