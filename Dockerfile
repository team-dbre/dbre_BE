# 최신 Slim Python 이미지 사용
FROM python:3.12.6-slim

# 작업 디렉토리 설정
WORKDIR /app

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# 필수 의존성 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install "poetry==$POETRY_VERSION"

# 의존성 파일만 먼저 복사
COPY pyproject.toml poetry.lock ./

# 의존성 설치
RUN poetry install --no-root --no-interaction --no-ansi

# 나머지 소스코드 복사
COPY . .