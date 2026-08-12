# Docker deployment

This setup runs LRMS with PostgreSQL, Gunicorn, and WhiteNoise. PostgreSQL data and user-uploaded media are stored in Docker named volumes, so `docker compose down` does not delete them.

## Run locally on any Docker-enabled computer

1. Copy `.env.docker.example` to `.env` and replace `SECRET_KEY` and `POSTGRES_PASSWORD` with strong values. The existing `.env` is also read by Compose, so its variables may be updated instead.
2. Run `docker compose up --build`.
3. Open `http://localhost:8000`.

The first start automatically applies migrations. To create the first tenant and administrator, set `BOOTSTRAP_LRMS=true` and a strong `BOOTSTRAP_ADMIN_PASSWORD` in `.env`, start once, then set `BOOTSTRAP_LRMS=false` again. This command is idempotent, but leaving bootstrap credentials in a deployment environment is not recommended.

Run detached with `docker compose up --build -d`; inspect logs with `docker compose logs -f web`; stop services with `docker compose down`. Do not use `docker compose down -v` unless intentionally deleting all database and uploaded-media data.

## Production

Use a unique random `SECRET_KEY` and database password. Set `DJANGO_DEBUG=False`, your public hostname in `ALLOWED_HOSTS`, its `https://` URL in `CSRF_TRUSTED_ORIGINS`, and set `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True`, and a suitable `SECURE_HSTS_SECONDS` value. Put a TLS-terminating reverse proxy or managed load balancer in front of port 8000. For multi-instance deployments, run database migrations as a release/job step rather than concurrently in every web replica.
