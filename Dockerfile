# Build the compiled Tailwind stylesheet from its locked npm dependencies.
FROM node:22-alpine AS frontend

WORKDIR /app/theme/static_src
COPY theme/static_src/package.json theme/static_src/package-lock.json ./
RUN npm ci
COPY theme/static_src/ ./
RUN npm run build


# Build Python wheels once so the runtime image does not need build tooling.
FROM python:3.12-slim AS python-builder

WORKDIR /wheels
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN addgroup --system lrms && adduser --system --ingroup lrms lrms
COPY --from=python-builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --chown=lrms:lrms . .
COPY --from=frontend --chown=lrms:lrms /app/theme/static/css/dist/styles.css /app/theme/static/css/dist/styles.css

# Keep static assets in the image; WhiteNoise serves them without a separate web server.
RUN python manage.py collectstatic --noinput

COPY --chown=lrms:lrms docker-entrypoint.sh /usr/local/bin/docker-entrypoint
RUN chmod 755 /usr/local/bin/docker-entrypoint && mkdir -p /app/media && chown -R lrms:lrms /app/media

USER lrms
EXPOSE 8000

ENTRYPOINT ["docker-entrypoint"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
