#!/usr/bin/env bash

# 스크립트 설정: 오류 발생 시 즉시 종료, 정의되지 않은 변수 사용 금지
set -euo pipefail

# 컬러 설정
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_NC='\033[0m' # No Color

echo -e "${COLOR_GREEN}Running Black...${COLOR_NC}"
poetry run black .

echo -e "${COLOR_GREEN}Running isort...${COLOR_NC}"
poetry run isort .

echo -e "${COLOR_GREEN}Running Mypy...${COLOR_NC}"
poetry run mypy .

echo -e "${COLOR_GREEN}Running Django Tests...${COLOR_NC}"
python manage.py test

echo -e "${COLOR_GREEN}All checks passed successfully!${COLOR_NC}"
