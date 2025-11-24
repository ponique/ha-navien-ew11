import json
import os
from logger import setup_logger

class ConfigManager:
    def __init__(self, config_path="/data/options.json"):
        self.config_path = config_path
        self._config = {}
        self.logger = setup_logger("ConfigManager")
        self._load_config()

    def _load_config(self):
        """Load configuration from HA options.json"""
        try:
            # HA Add-on 환경이 아닐 경우를 대비한 로컬 테스트 경로 지원
            if not os.path.exists(self.config_path):
                # 로컬 테스트용 더미 파일 혹은 환경 변수 처리 (옵션)
                pass
            
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
                self.logger.info(f"Loaded HA options from {self.config_path}")
        except Exception as e:
            self.logger.warning(f"Failed to load HA options: {e}. Using defaults.")

    @property
    def socket_ip(self):
        return self._config.get("ew11_ip", "")

    @property
    def socket_port(self):
        return self._config.get("ew11_port", 8888)

    @property
    def mqtt_server(self):
        return self._config.get("mqtt_server", "core-mosquitto")

    @property
    def mqtt_port(self):
        return self._config.get("mqtt_port", 1883)

    @property
    def mqtt_username(self):
        return self._config.get("mqtt_username", "")

    @property
    def mqtt_password(self):
        return self._config.get("mqtt_password", "")

    @property
    def root_topic(self):
        return "navien"

    @property
    def homeassistant_root_topic(self):
        return "homeassistant"

    def validate_config(self):
        """Validate essential configuration"""
        if not self.socket_ip:
            self.logger.critical("EW11 IP Address is missing! Please configure the Add-on.")
            return False
        return True
    
    def print_config(self):
        """Print current config (masking password)"""
        self.logger.info(f"Target EW11: {self.socket_ip}:{self.socket_port}")
        self.logger.info(f"MQTT Broker: {self.mqtt_server}:{self.mqtt_port}")