FROM python:3.13-slim

WORKDIR /app

# ENV

# PostgreSQL 의존성 설치
RUN apt-get update \
    && apt-get install -y libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Poetry 설치
RUN pip install "poetry==$POETRY_VERSION"
ENV PATH="$POETRY_HOME/bin:$PATH"

# 의존성 파일 복사 및 설치
COPY pyproject.toml poetry.lock alembic.ini ./
RUN poetry install --no-root --no-dev


CMD ["sh", "-c", "poetry lock --no-update && poetry install && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]

