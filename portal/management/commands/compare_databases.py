"""Look-only comparison of two databases: how many rows each table has in the SOURCE (the old test portal database) and in the TARGET
(the database the portal will use from now on).  Nothing is changed in either.

  $env:DATABASE_URL        = the TARGET (quotation-db, External URL)
  $env:SOURCE_DATABASE_URL = the SOURCE (the test portal database, External URL)
  python manage.py compare_databases
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def _connect(url):
    """A plain connection to the source database (psycopg 3, or psycopg2 when that is what is installed)."""
    try:
        import psycopg
        return psycopg.connect(url)
    except ImportError:
        import psycopg2
        return psycopg2.connect(url)


def counts(conn):
    out = {}
    with conn.cursor() as c:
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        for (t,) in c.fetchall():
            c.execute('SELECT count(*) FROM public."%s"' % t)
            out[t] = c.fetchone()[0]
    return out


class Command(BaseCommand):
    help = "Show the row counts of every table in the source and target databases (changes nothing)."

    def handle(self, *args, **o):
        url = os.environ.get("SOURCE_DATABASE_URL")
        if not url:
            raise CommandError("Set SOURCE_DATABASE_URL to the External URL of the test portal database first.")
        source = _connect(url)
        try:
            src = counts(source)
        finally:
            source.close()
        dst = counts(connection)
        self.stdout.write("%-42s %9s %9s" % ("table", "source", "target"))
        skip = ("django_", "auth_permission", "django_content_type")
        for t in sorted(set(src) | set(dst)):
            if t.startswith(skip) or (src.get(t, 0) == 0 and dst.get(t, 0) == 0):
                continue
            self.stdout.write("%-42s %9s %9s" % (t, src.get(t, "-"), dst.get(t, "-")))
        self.stdout.write(self.style.SUCCESS("Nothing was changed."))
