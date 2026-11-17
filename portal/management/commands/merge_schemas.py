"""One-time move of the old apps' data into the portal's main database area.

The old live database keeps three separate areas (schemas): public (quotations), cleaning (Cleaning Manager) and materials (store).
The portal reads only `public`.  This command runs merge_schemas.sql, which moves the cleaning and store tables into `public` and merges the
three user lists.  It changes nothing until you run it WITHOUT --dry-run, it refuses to run if the portal has already built its own
tables there, and the whole move is one transaction (all or nothing).  Nothing is deleted: the old areas stay.

  python manage.py merge_schemas --dry-run     (only looks and prints)
  python manage.py merge_schemas               (does it)
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Move the cleaning and store tables of the old live database into the main (public) area."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="only show what is there")

    def handle(self, *args, **o):
        if connection.vendor != "postgresql":
            raise CommandError("This is only for the live Postgres database (set DATABASE_URL to it first).")
        with connection.cursor() as c:
            c.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('public','cleaning','materials')")
            found = {r[0] for r in c.fetchall()}
            missing = {"public", "cleaning", "materials"} - found
            if missing:
                raise CommandError("These areas are not in this database: %s. Is DATABASE_URL the quotation database?" % ", ".join(sorted(missing)))
            c.execute("SELECT count(*) FROM public.auth_user")
            self.stdout.write("Logins in public: %d" % c.fetchone()[0])
            for sch in ("cleaning", "materials"):
                c.execute("SELECT count(*) FROM %s.auth_user" % sch)
                n_users = c.fetchone()[0]
                c.execute("SELECT count(*) FROM pg_tables WHERE schemaname = %s", [sch])
                self.stdout.write("%-10s %d tables, %d logins" % (sch + ":", c.fetchone()[0], n_users))
            c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND (tablename LIKE 'cleaning\\_%%' OR tablename LIKE 'store\\_%%')")
            clash = [r[0] for r in c.fetchall()]
            if clash:
                raise CommandError("The main area already has tables of the portal (%s ...). Merging now would clash. "
                                   "The portal must NOT have been started on this database before the merge. Stop here and ask for help."
                                   % ", ".join(clash[:3]))
            c.execute("SELECT count(*) FROM public.django_migrations WHERE app = 'portal'")
            if c.fetchone()[0]:
                raise CommandError("The portal has already created its tables in this database. Stop here and ask for help.")
        if o["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: nothing changed. It is safe to run it without --dry-run."))
            return
        sql_file = settings.BASE_DIR / "merge_schemas.sql"
        sql = sql_file.read_text(encoding="utf-8")
        with connection.cursor() as c:
            c.execute(sql)           # the script is one BEGIN ... COMMIT: all or nothing
        self.stdout.write(self.style.SUCCESS("Done. The cleaning and store tables and the logins are now in the main area. "
                                             "Now point the portal service at this database and deploy."))
