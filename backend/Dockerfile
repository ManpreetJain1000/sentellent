FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/

RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["sh", "-c", "alembic upgrade head && exec \"$@\"", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
