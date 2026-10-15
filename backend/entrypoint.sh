#!/bin/sh
set -eu

echo "[FamilyOS] applying database migrations"
python manage.py migrate --noinput

echo "[FamilyOS] collecting static files"
python manage.py collectstatic --noinput

echo "[FamilyOS] bootstrapping global admin and initial household"
python manage.py bootstrap_famuhle

echo "[FamilyOS] starting ASGI server on 0.0.0.0:8000"
exec daphne \
  --bind 0.0.0.0 \
  --port 8000 \
  --access-log - \
  config.asgi:application
