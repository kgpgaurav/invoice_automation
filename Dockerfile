FROM node:24-bookworm-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
RUN pip install --no-cache-dir uv==0.7.2
WORKDIR /app/backend
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY --from=ui /ui/dist /app/ui
COPY docs/benchmarks/openai-rates-2026-11-12.json /app/rates.json
RUN useradd --create-home --uid 10001 app
ENV PATH="/opt/venv/bin:$PATH" FRONTEND_DIRECTORY=/app/ui PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["python", "-m", "scripts.hosted", "api"]
