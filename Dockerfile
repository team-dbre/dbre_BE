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
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONPATH="/app:$PYTHONPATH"

# 시스템 의존성 설치 및 캐시 정리
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry==$POETRY_VERSION" \
    && rm -rf /root/.cache/pip

# Poetry 설정
ENV PATH="${POETRY_HOME}/bin:$PATH"

# 의존성 파일만 먼저 복사
COPY pyproject.toml poetry.lock ./

# Poetry 의존성 설치
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# 소스 코드 복사
COPY . .

# 실행 명령
CMD ["sh", "-c", "poetry run python manage.py migrate && poetry run gunicorn --bind 0.0.0.0:8000 dbre_BE.wsgi:application"]
