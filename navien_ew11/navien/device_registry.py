import json
import os
from logger import setup_logger

class DeviceRegistry:
    def __init__(self, wallpad):
        self.wallpad = wallpad
        self.logger = setup_logger("DeviceRegistry")
        self.load_success = False
        
        # 같은 폴더에 있는 config.json 로드
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.full_config = json.load(f)
                self.load_success = True
                self.logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to load {config_path}: {e}")
            self.full_config = {}

        self.devices_config = self.full_config.get('devices', {})
        self.room_templates = self.full_config.get('room_templates', {})
        
        # 전열교환기 속도 매핑 (HA <-> Hex)
        self._packet_mappings = {
            'percentage': {'00': '0', '01': '1', '02': '2', '03': '3'},
        }

    def _make_temp_cmd(self, v):
        """HA 온도 값(float)을 정수형 16진수 문자열로 변환"""
        try: 
            return hex(int(float(v)))[2:].zfill(2)
        except: 
            return '18' # 기본값 24도

    def _convert_percentage_to_hex(self, v):
        """HA Fan Speed(%)를 전열교환기 16진수 명령으로 변환"""
        try:
            val = int(float(v))
            if val == 0: return '00'
            elif val <= 35: return '01' # 약
            elif val <= 70: return '02' # 중 (자동)
            else: return '03' # 강
        except: return '01'

    def _generate_child_devices(self, config):
        """config.json에서 방 이름과 ID 목록 추출"""
        room_config = config.get('room_config', {})
        if not room_config.get('enabled', False): return [], []
        rooms = room_config.get('rooms', [])
        return ([r['name'] for r in rooms], [r['control_id'] for r in rooms])

    def register_all_devices(self):
        """설정된 모든 장치 등록 시작"""
        for key, conf in self.devices_config.items():
            if key == 'heat_exchanger': self._register_heat_exchanger(conf)
            elif key == 'gas_valve': self._register_gas_valve(conf)
            elif key == 'lights': self._register_lights(conf)
            elif key == 'heating': self._register_heating(conf)
            elif key == 'elevator': self._register_elevator(conf)

    def _register_heat_exchanger(self, config):
        d = self.wallpad.add_device(config['name'], config['id'], config['subid'], config['class'], optional_info=config.get('optional_info', {}))
        
        # 가용성 (항상 online)
        d.register_status('01', 'availability', r'()', 'availability_topic', process_func=lambda v: 'online')
        
        # 전원 상태 (3번째 바이트)
        d.register_status('81', 'power', r'0500([0-9a-fA-F]{2})', 'state_topic', process_func=lambda v: 'OFF' if v == '00' else 'ON')
        
        # 풍량 상태 (4번째 바이트: Mode) - 01:약, 02:자동(중), 03:강
        d.register_status('81', 'percentage', r'0500[0-9a-fA-F]{2}([0-9a-fA-F]{2})', 'percentage_state_topic', 
                          process_func=lambda v: {'01': '1', '02': '2', '03': '3'}.get(v, '1'))

        # 명령 (전원, 풍량)
        d.register_command('41', 'power', 'command_topic', process_func=lambda v: '01' if v == 'ON' else '00')
        d.register_command('42', 'percentage', 'percentage_command_topic', process_func=self._convert_percentage_to_hex)

    def _register_gas_valve(self, config):
        d = self.wallpad.add_device(config['name'], config['id'], config['subid'], config['class'], optional_info=config.get('optional_info', {}))
        
        d.register_status('01', 'availability', r'()', 'availability_topic', process_func=lambda v: 'online')
        
        # 가스 상태: 04=잠김(ON), 02=열림(OFF)
        d.register_status('81', 'power', r'0200([0-9a-fA-F]{2})', 'state_topic', process_func=lambda v: 'ON' if v == '04' else 'OFF') 
        
        # 명령: 안전을 위해 '잠금(00)' 명령만 허용 (앱에서 ON하든 OFF하든 잠금 시도)
        d.register_command('41', 'power', 'command_topic', process_func=lambda v: '00') 

    def _register_lights(self, config):
        childs, c_ids = self._generate_child_devices(config)
        d = self.wallpad.add_device(config['name'], config['id'], config['subid'], config['class'], child_devices=childs, optional_info=config.get('optional_info', {}))
        
        # 조명 상태 패킷: 04 00 [방1] [방2] [방3] ...
        # Regex 자동 생성
        regex_pattern = r'0400'
        for _ in childs:
            regex_pattern += r'([0-9a-fA-F]{2})'
        regex_pattern += r'.*'

        # 상태 파싱 (01=ON, 그외 OFF)
        d.register_status('81', 'power', regex_pattern, 'state_topic', process_func=lambda v: 'ON' if v == '01' else 'OFF')
        
        # 명령 (41 01 01 / 41 01 00)
        d.register_command('41', 'power', 'command_topic', controll_id=c_ids, process_func=lambda v: '01' if v == 'ON' else '00')

    def _register_heating(self, config):
        childs, c_ids = self._generate_child_devices(config)
        d = self.wallpad.add_device(config['name'], config['id'], config['subid'], config['class'], child_devices=childs, optional_info=config.get('optional_info', {}))
        
        # 난방 통합 패킷: 0D 00 (PowerMask) (AwayMask) 00 00 (CurTempString) (TargetTempString)
        status_regex = r'0D00([0-9a-fA-F]{2})([0-9a-fA-F]{2})0000([0-9a-fA-F]{10})([0-9a-fA-F]{10}).*'

        # 1. 전원 (Bitmask)
        d.register_status('81', 'power', status_regex, 'mode_state_topic', 
                          process_func=lambda v, idx=0: 'heat' if (int(v, 16) & (1 << idx)) else 'off')

        # 2. 외출 (Bitmask)
        d.register_status('81', 'away_mode', status_regex, 'away_mode_state_topic',
                          process_func=lambda v, idx=0: 'ON' if (int(v, 16) & (1 << idx)) else 'OFF')

        # 3. 현재/목표 온도 (문자열 슬라이싱, 정수형)
        def get_temp_from_hex_string(hex_str, idx):
            try: 
                # 10바이트 문자열에서 idx*2 부터 2글자 추출
                return int(hex_str[idx*2 : idx*2+2], 16)
            except: return 0

        d.register_status('81', 'currenttemp', status_regex, 'current_temperature_topic', process_func=get_temp_from_hex_string)
        d.register_status('81', 'targettemp', status_regex, 'temperature_state_topic', process_func=get_temp_from_hex_string)

        # 명령 (43:전원, 44:온도, 45:외출)
        d.register_command('43', 'power', 'mode_command_topic', controll_id=c_ids, process_func=lambda v: '01' if v == 'heat' else '00')
        d.register_command('44', 'targettemp', 'temperature_command_topic', controll_id=c_ids, process_func=self._make_temp_cmd)
        d.register_command('45', 'away_mode', 'away_mode_command_topic', controll_id=c_ids, process_func=lambda v: '01' if v == 'ON' else '00')

    def _register_elevator(self, config):
        d = self.wallpad.add_device(config['name'], config['id'], config['subid'], config['class'], optional_info=config.get('optional_info', {}))
        
        # 엘베 상태 (호출시 44)
        d.register_status('81', 'power', r'0300([0-9a-fA-F]{2})', 'state_topic', process_func=lambda v: 'ON' if v == '44' else 'OFF')
        
        # 호출 명령 (10)
        d.register_command('43', 'power', 'command_topic', process_func=lambda v: '10')
