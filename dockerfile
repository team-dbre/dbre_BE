# 최신 Slim Python 이미지 사용
FROM python:3.12.6-slim

# 작업 디렉토리 설정
WORKDIR /app

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.0.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# PostgreSQL 및 기타 의존성 설치
RUN apt-get update && \
    apt-get install -y libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Poetry 설치
RUN pip install "poetry==$POETRY_VERSION"
ENV PATH="${POETRY_HOME}/bin:$PATH"

# 소스 코드 복사 (전체 프로젝트 먼저 복사)
COPY . .

# Poetry 의존성 설치 (소스 코드 복사 후 설치)
RUN poetry install --no-root --no-interaction --no-ansi || exit 1

# Django용 명령어 실행
CMD ["sh", "-c", "poetry run python manage.py collectstatic --noinput && \
                 poetry run python manage.py migrate && \
                 poetry run gunicorn --bind 0.0.0.0:8000 my_project.wsgi:application"]