FROM ghcr.io/astral-sh/uv:python3.12-alpine

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apk add --no-cache \
    postgresql-dev \
    gcc \
    musl-dev

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY src ./src

CMD ["uv", "run", "python", "src/__main__.py"]
