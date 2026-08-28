FROM python:3.13-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "serum-mcp"]
