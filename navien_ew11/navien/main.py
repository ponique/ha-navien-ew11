#!/usr/bin/env python3
import sys
import time
import signal
from config_manager import ConfigManager
from wallpad import Wallpad
from device_registry import DeviceRegistry
from logger import setup_logger

# Global instance for signal handler
wallpad_instance = None

def signal_handler(sig, frame):
    print(f"Received signal {sig}, shutting down...")
    if wallpad_instance:
        wallpad_instance.close()
    sys.exit(0)

def main():
    global wallpad_instance
    logger = setup_logger("main")
    
    # Register Signal Handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 1. HA 설정 로드
    config = ConfigManager()
    if not config.validate_config():
        logger.critical("Invalid configuration.")
        # 바로 죽지 않고 로그 확인용 대기
        time.sleep(30)
        return 1
    
    config.print_config()
    
    # 2. 월패드 초기화
    wallpad = Wallpad(config)
    wallpad_instance = wallpad
    
    # 3. 장치 등록
    registry = DeviceRegistry(wallpad)
    if not registry.load_success:
        logger.critical("Failed to load navien/config.json. Exiting.")
        time.sleep(30)
        return 1
        
    registry.register_all_devices()
    logger.info(f"System initialized with {len(wallpad._device_list)} devices.")
    
    # 4. 실행
    try:
        wallpad.listen()
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")
        time.sleep(30)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
