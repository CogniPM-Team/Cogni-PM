# CogniPM in one image: the website (built here) and the API that serves it. PostgreSQL is a separate
# container: see docker-compose.yml, which starts both with one command.
#
#   docker compose up --build        then open http://localhost:8000

# ---- 1. build the website -------------------------------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. the API, with the built website beside it ---------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Installed in place (not copied into site-packages) because the code finds the website and the gateway
# relative to the repository layout: /app/backend and /app/frontend/dist.
COPY backend/ ./backend/
RUN pip install -e ./backend
COPY --from=web /web/dist ./frontend/dist

# The app does not need to be root. Secrets are NOT in this image: they arrive as environment variables at
# run time (docker-compose.yml reads them from your .env).
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"
CMD ["uvicorn", "cognipm.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
