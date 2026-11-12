# One image for the whole site.  Build:  docker build -t dehlsen .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=portal_site.settings

# The Linux libraries WeasyPrint needs to draw the quotation PDFs
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# gather the static files once, at build time (throw-away key and address, used only here)
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-key-build-only-key-build-only-key DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser /data /app
ENV SQLITE_PATH=/data/db.sqlite3 WEB_CONCURRENCY=1
EXPOSE 8000
USER appuser
CMD ["sh", "docker-start.sh"]
