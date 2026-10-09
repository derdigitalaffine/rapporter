#!/bin/sh
set -eu

echo "[fam-uh-le] applying database migrations"
python manage.py migrate --noinput

echo "[fam-uh-le] collecting static files"
python manage.py collectstatic --noinput

echo "[fam-uh-le] bootstrapping initial household"
python manage.py bootstrap_famuhle

echo "[fam-uh-le] starting gunicorn on 0.0.0.0:8000"
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
