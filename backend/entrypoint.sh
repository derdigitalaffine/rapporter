#!/bin/sh
set -eu

echo "[FamilyOS] applying database migrations"
python manage.py migrate --noinput

echo "[FamilyOS] collecting static files"
python manage.py collectstatic --noinput

echo "[FamilyOS] bootstrapping global admin and initial household"
python manage.py bootstrap_famuhle

echo "[FamilyOS] starting gunicorn on 0.0.0.0:8000"
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
