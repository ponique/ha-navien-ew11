ARG BUILD_FROM
FROM $BUILD_FROM

# 1. 로그 설정 및 언어 설정
ENV PYTHONUNBUFFERED=1
ENV LANG C.UTF-8

# 2. 필수 패키지 설치
RUN apk add --no-cache python3 py3-pip

# 3. 파일 복사
WORKDIR /app
COPY . /app

# 4. 파이썬 라이브러리 설치
RUN pip3 install --no-cache-dir -r navien/requirements.txt --break-system-packages

# ★[핵심] S6 서비스 등록 (CMD 대신 사용)
# - 서비스 디렉토리 생성
RUN mkdir -p /etc/services.d/navien

# - 실행 스크립트 생성 (윈도우 엔터키 문제 없음)
# - with-contenv bashio: HA 애드온 환경변수를 로드하는 표준 쉘
# - exec: 프로세스를 파이썬으로 교체하여 신호 처리 보장
RUN printf "#!/usr/bin/with-contenv bashio\ncd /app/navien\nexec python3 main.py\n" > /etc/services.d/navien/run

# - 실행 권한 부여
RUN chmod +x /etc/services.d/navien/run
