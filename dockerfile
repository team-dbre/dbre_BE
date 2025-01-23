# 최신 Slim Python 이미지 사용
FROM python:3.12.6-slim

# 작업 디렉토리 설정
WORKDIR /app

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.0.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# PostgreSQL 및 기타 의존성 설치
RUN apt-get update && \
    apt-get install -y libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Poetry 설치
ENV POETRY_VERSION=2.0.0
RUN pip install "poetry==$POETRY_VERSION"
ENV PATH="${POETRY_HOME}/bin:$PATH"

# 프로젝트 의존성 파일 복사 및 설치
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --without dev

# 프로젝트 소스 코드 복사
COPY . .

# Django용 명령어 실행
CMD ["sh", "-c", "poetry install --no-root && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]