#!/bin/bash
set -e

# 현재 위치를 프로젝트 루트로 설정
cd /root/dbre_BE

# 환경 변수 로드
source .env.prod

# Docker 컨테이너 재시작
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build

# 데이터베이스 마이그레이션
docker-compose -f docker-compose.prod.yml exec -T web poetry run python manage.py migrate --noinput

# 정적 파일 수집
docker-compose -f docker-compose.prod.yml exec -T web poetry run python manage.py collectstatic --noinput

# Nginx 재시작
docker-compose -f docker-compose.prod.yml exec -T nginx nginx -s reload
