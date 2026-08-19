FROM node:24-alpine AS frontend

WORKDIR /frontend

COPY dedodaded-UI/package.json dedodaded-UI/package-lock.json ./
RUN npm ci

COPY dedodaded-UI ./
RUN npm run build


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY dedodaded ./dedodaded
COPY --from=frontend /dedodaded/static ./dedodaded/static

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin panel

USER panel

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:8080' + os.getenv('PANEL_BASE_PATH', '') + '/api/health', timeout=3)" || exit 1

CMD ["dedodaded"]
