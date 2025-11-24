import logging
import sys

def setup_logger(name="navien", level="INFO"):
    """Set up a logger with consistent formatting."""
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 있으면 추가하지 않음 (중복 로그 방지)
    if logger.handlers:
        return logger
    
    # 로그 레벨 설정
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # 콘솔 핸들러 (stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    
    # 포맷 설정 (날짜 시간 - 모듈명 - 레벨 - 메시지)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger