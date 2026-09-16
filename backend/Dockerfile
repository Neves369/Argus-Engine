FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY policies ./policies
COPY sources.json ./sources.json
COPY tools.json ./tools.json
COPY tools.json.example ./tools.json.example

RUN pip install .

EXPOSE 8000

# $PORT é injetado pelo Railway (porta de escuta dinâmica); fora dele, 8000.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]