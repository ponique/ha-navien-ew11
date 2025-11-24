import logging
from .const import PACKET_PREFIX
from .models import DeviceType, DeviceKey, DeviceState
from homeassistant.const import Platform
from homeassistant.components.climate.const import HVACMode

LOGGER = logging.getLogger(__name__)

class NavienController:
    # ... (생략된 함수들은 이전과 동일) ...

    def _check_integrity(self, pkt):
        # ... (생략됨) ...
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

        # ... (Light and Thermostat sections remain the same) ...

        # 3. Fan (0x32) - ★ [최종 수정] Power 우선 체크 및 상태 파싱
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
                
                state = {
                    "state": is_on, 
                    "percentage": pct,
                    "preset_mode": preset
                }
                self._update(DeviceType.VENTILATION, 1, state)
        
        # ... (Gas, Elevator, _update, make_cmd remains the same) ...

    # [make_cmd] - ★ [핵심 수정] set_speed의 조건문 논리 오류 해결
    def make_cmd(self, dtype, idx, action, **kwargs):
        # ... (초기 변수 설정 생략) ...

        elif dtype == DeviceType.VENTILATION:
            if action == "set_speed":
                cmd = 0x42
                pct = kwargs['pct']
                
                # ★ [수정됨] 논리 순서 변경: Auto, Low, Medium, High 순으로 명확히 구분
                val = 0x00 # Default OFF
                
                if pct == 0:
                    val = 0x00
                elif pct == 50:
                    val = 0x04 # Auto (50%는 Auto 전용값)
                elif pct <= 33:
                    val = 0x01 # Low
                elif pct <= 66:
                    val = 0x02 # Medium
                elif pct <= 100:
                    val = 0x03 # High
                
                payload = [0x01, val]
            elif action == "off":
                cmd = 0x41
                payload = [0x01, 0x00]
            elif action == "on":
                cmd = 0x41
                payload = [0x01, 0x01]
        
        # ... (나머지 make_cmd 로직은 동일) ...
        base = [0xF7, did, sub, cmd] + payload
        # ... (checksums) ...
        return bytes(base + [xor, add & 0xFF])
