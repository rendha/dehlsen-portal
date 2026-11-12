#!/bin/sh
# Starts the site: wait for the database -> update the tables -> make the groups -> run the web server.
set -e
CHECK='import django; django.setup(); from django.db import connection; connection.ensure_connection()'
tries=0
until python -c "$CHECK" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge "${DB_WAIT_TRIES:-36}" ]; then
        echo "The database did not answer after $tries tries. Check DATABASE_URL."
        python -c "$CHECK" || true
        exit 1
    fi
    echo "Waiting for the database ($tries) ..."
    sleep "${DB_WAIT_SECONDS:-5}"
done
python manage.py migrate --noinput
python manage.py setup_roles || true
exec gunicorn portal_site.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --timeout 120 --access-logfile -
