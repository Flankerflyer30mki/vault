#!/bin/sh
set -e
# Migrations run once per deploy: as Render's pre-deploy command (preferred), or here
# when RUN_MIGRATIONS=1 on a single-instance service.
if [ "$RUN_MIGRATIONS" = "1" ]; then
  python manage.py migrate --noinput
fi
exec gunicorn vault_core.wsgi:application -c gunicorn.conf.py
