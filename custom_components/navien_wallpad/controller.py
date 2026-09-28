import logging
from .const import PACKET_PREFIX
from .transport import PACKET_LOGGER, WIRE_LOGGER, _debug_event
from .models import DeviceType, DeviceKey, DeviceState
from homeassistant.const import Platform
from homeassistant.components.climate.const import HVACMode

LOGGER = logging.getLogger(__name__)

class NavienController:
    def __init__(self, gateway):
        self.gateway = gateway
        self._rx_buf = bytearray()
        self._debug_frame_id = 0

    def feed(self, data: bytes):
        self._rx_buf.extend(data)
        while True:
            try:
                start = self._rx_buf.index(PACKET_PREFIX)
                if start > 0:
                    if WIRE_LOGGER.isEnabledFor(logging.DEBUG):
                        self._log_drop("PREFIX_SKIP", self._rx_buf[:start])
                    del self._rx_buf[:start]
            except ValueError:
                self._log_drop("NO_PREFIX", self._rx_buf)
                self._rx_buf.clear()
                break

            if len(self._rx_buf) < 7: break

            valid = False
            for l in range(7, min(len(self._rx_buf)+1, 60)):
                candidate = self._rx_buf[:l]
                if self._check_integrity(candidate):
                    self._debug_frame_id += 1
                    if PACKET_LOGGER.isEnabledFor(logging.DEBUG):
                        _debug_event(PACKET_LOGGER, "RX_FRAME",
                                     connection=self.gateway.conn._debug_connection_id,
                                     frame_id=self._debug_frame_id, length=len(candidate),
                                     raw=candidate.hex(), device=candidate[1], sub=candidate[2],
                                     command=candidate[3], declared_length=candidate[4],
                                     checksum="OK", framing="CANDIDATE_ACCEPTED")
                    self._parse(candidate, frame_id=self._debug_frame_id)
                    del self._rx_buf[:l]
                    valid = True
                    break
            
            if not valid:
                if len(self._rx_buf) > 60:
                    if WIRE_LOGGER.isEnabledFor(logging.DEBUG):
                        self._log_drop("BUFFER_LIMIT", self._rx_buf[:1])
                    del self._rx_buf[0]
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

    def _log_drop(self, reason, data):
        if data and WIRE_LOGGER.isEnabledFor(logging.DEBUG):
            _debug_event(WIRE_LOGGER, "RX_DROP",
                         connection=self.gateway.conn._debug_connection_id,
                         reason=reason, kind="UNFRAMED", length=len(data), raw=data.hex())

    def _log_parse(self, pkt, frame_id, result, dtype=None, index=None, state=None):
        if PACKET_LOGGER.isEnabledFor(logging.DEBUG):
            _debug_event(PACKET_LOGGER, "RX_PARSE",
                         connection=self.gateway.conn._debug_connection_id,
                         frame_id=frame_id, device=pkt[1], command=pkt[3], result=result,
                         device_type=dtype.name if dtype is not None else None,
                         index=index, state=state)

    def _parse(self, pkt, *, frame_id=None):
        dev_id = pkt[1]
        cmd = pkt[3]
        
        try:
            data_len = pkt[4]
            if len(pkt) < 5 + data_len + 2:
                self._log_parse(pkt, frame_id, "INVALID_LENGTH")
                return
            data = pkt[5:5+data_len]
        except IndexError:
            self._log_parse(pkt, frame_id, "INVALID_LENGTH")
            return

        # 1. Light (0x0E)
        if dev_id == 0x0E and cmd == 0x81:
            if len(data) >= 2: 
                for i, val in enumerate(data[1:]):
                    self._log_parse(pkt, frame_id, "KNOWN", DeviceType.LIGHT, i+1, val == 0x01)
                    self._update(DeviceType.LIGHT, i+1, val == 0x01)
            else:
                self._log_parse(pkt, frame_id, "INVALID_PAYLOAD", DeviceType.LIGHT)

        # 2. Thermostat (0x36) - ★ [최종 복구: 값 할당 단계 교정]
        elif dev_id == 0x36 and cmd == 0x81:
            if len(data) >= 5:
                pwr_mask = data[1]
                away_mask = data[2]
                temp_data = data[5:]
                room_count = len(temp_data) // 2
                if room_count == 0:
                    self._log_parse(pkt, frame_id, "IGNORED", DeviceType.THERMOSTAT)
                
                for i in range(room_count):
                    is_on = bool(pwr_mask & (1 << i))
                    is_away = bool(away_mask & (1 << i))
                    
                    # Raw data is [Set Value, Current Value]
                    raw_set_val = self._parse_temp(temp_data[i*2])   
                    raw_cur_val = self._parse_temp(temp_data[i*2+1]) 
                    
                    if raw_cur_val == 0 and raw_set_val == 0:
                        self._log_parse(pkt, frame_id, "IGNORED", DeviceType.THERMOSTAT, i+1)
                        continue

                    state = {
                        "hvac_mode": HVACMode.HEAT if is_on else HVACMode.OFF,
                        "preset_mode": "away" if is_away else "none",
                        # ★ [FINAL FIX] UI에 정상적으로 보이도록 Swapped Assignment
                        "current_temp": raw_cur_val,  # HA Current reads the packet's Current
                        "target_temp": raw_set_val   # HA Target reads the packet's Set
                    }
                    self._log_parse(pkt, frame_id, "KNOWN", DeviceType.THERMOSTAT, i+1, state)
                    self._update(DeviceType.THERMOSTAT, i+1, state)
            else:
                self._log_parse(pkt, frame_id, "INVALID_PAYLOAD", DeviceType.THERMOSTAT)

        # 3. Fan (0x32)
        elif dev_id == 0x32 and cmd == 0x81:
            if len(data) >= 3:
                pwr_byte = data[1]
                mode_byte = data[2]
                
                is_on = (pwr_byte != 0x00)
                pct = 0
                preset = None 
                
                if is_on:
                    if mode_byte == 0x02: 
                        preset = "auto"
                        pct = 50 
                    elif mode_byte == 0x03:
                        preset = "high"
                        pct = 100
                    else: 
                        preset = "low" 
                        pct = 33
                
                state = {"state": is_on, "percentage": pct, "preset_mode": preset}
                self._log_parse(pkt, frame_id, "KNOWN", DeviceType.VENTILATION, 1, state)
                self._update(DeviceType.VENTILATION, 1, state)
            else:
                self._log_parse(pkt, frame_id, "INVALID_PAYLOAD", DeviceType.VENTILATION)

        # 4. Gas (0x12)
        elif dev_id == 0x12 and cmd == 0x81:
            if len(data) >= 2:
                # 0x02 is confirmed closed; keep the legacy 0x04 variant.
                is_closed = data[1] in (0x02, 0x04)
                self._log_parse(pkt, frame_id, "KNOWN", DeviceType.GASVALVE, 1, is_closed)
                self._update(DeviceType.GASVALVE, 1, is_closed)
            else:
                self._log_parse(pkt, frame_id, "INVALID_PAYLOAD", DeviceType.GASVALVE)

        # 5. Elevator (0x33)
        elif dev_id == 0x33 and cmd == 0x81:
            if len(data) >= 2:
                is_active = (data[1] == 0x44)
                self._log_parse(pkt, frame_id, "KNOWN", DeviceType.ELEVATOR, 1, is_active)
                self._update(DeviceType.ELEVATOR, 1, is_active)
            else:
                self._log_parse(pkt, frame_id, "INVALID_PAYLOAD", DeviceType.ELEVATOR)
        else:
            if PACKET_LOGGER.isEnabledFor(logging.DEBUG):
                _debug_type = next((dtype for dtype in DeviceType
                                    if dtype != DeviceType.UNKNOWN and dtype.value == dev_id), None)
                self._log_parse(pkt, frame_id,
                                "UNKNOWN_COMMAND" if _debug_type is not None else "UNKNOWN_DEVICE",
                                _debug_type)

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
            elif action == "off":
                cmd = 0x41
                payload = [0x01, 0x00] # Power OFF
            elif action == "on":
                cmd = 0x41
                payload = [0x01, 0x01] # Power ON

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
