import re
from functools import reduce

class ProtocolUtils:
    """Utilities for Navien RS485 protocol handling."""

    @staticmethod
    def xor(hexstring_array):
        """Calculate XOR checksum."""
        return format(reduce(lambda x, y: x ^ y, map(lambda x: int(x, 16), hexstring_array)), '02x')

    @staticmethod
    def add(hexstring_array):
        """Calculate ADD checksum."""
        return format(reduce(lambda x, y: x + y, map(lambda x: int(x, 16), hexstring_array)), '02x')[-2:]

    @staticmethod
    def is_valid(payload_hexstring):
        """
        Validate RS485 payload using checksums.
        Format: F7 ID SUB CMD LEN DATA... XOR ADD
        """
        # 2글자씩 잘라서 리스트로 변환
        payload_array = [payload_hexstring[i:i+2] for i in range(0, len(payload_hexstring), 2)]
        
        try:
            # 최소 길이 체크 (Header + ID + SubID + Cmd + Len + XOR + ADD = 7 bytes)
            if len(payload_array) < 7:
                return False
            
            # 길이 검증 (5번째 바이트가 데이터 길이)
            # 데이터 길이 + 헤더/메타데이터(5개) + 체크섬(2개) = 전체 길이
            data_len = int(payload_array[4], 16)
            if len(payload_array) != data_len + 7:
                return False

            # 체크섬 검증
            xor_val = ProtocolUtils.xor(payload_array[:-2])
            add_val = ProtocolUtils.add(payload_array[:-1])
            
            return (xor_val == payload_array[-2] and add_val == payload_array[-1])
            
        except (ValueError, IndexError):
            return False

    @staticmethod
    def parse_payload(payload_hexstring):
        """Parse basic components from hex string."""
        # 기본 구조 파싱 (ID, SubID, Command 등)
        pattern = (
            r'f7'
            r'(?P<device_id>0e|12|32|33|36)'
            r'(?P<device_subid>[0-9a-f]{2})'
            r'(?P<message_flag>[0-9a-f]{2})'
            r'(?:[0-9a-f]{2})' # Length byte (skip)
            r'(?P<data>[0-9a-f]*)'
            r'(?P<xor>[0-9a-f]{2})'
            r'(?P<add>[0-9a-f]{2})'
        )
        
        match = re.match(pattern, payload_hexstring, re.IGNORECASE)
        return match.groupdict() if match else None