#!/bin/sh
set -eu

python manage.py migrate --noinput

bootstrap_flag=$(printf '%s' "${BOOTSTRAP_LRMS:-false}" | tr '[:upper:]' '[:lower:]')
case "$bootstrap_flag" in
  true|1|yes|on)
    if [ -z "${BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
      echo "BOOTSTRAP_LRMS is enabled but BOOTSTRAP_ADMIN_PASSWORD is empty." >&2
      exit 1
    fi
    python manage.py bootstrap_lrms \
      --tenant-name "${BOOTSTRAP_TENANT_NAME:-Demo Tenant}" \
      --tenant-slug "${BOOTSTRAP_TENANT_SLUG:-demo-tenant}" \
      --username "${BOOTSTRAP_ADMIN_USERNAME:-admin}" \
      --password "${BOOTSTRAP_ADMIN_PASSWORD}"
    ;;
esac

exec "$@"
