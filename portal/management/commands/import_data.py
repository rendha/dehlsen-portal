"""py manage.py import_data  -  copies ALL the data of your three old websites into this one site:
    quotations (rates, panels, every quotation ...)   materials (customers, lines, stock, payments ...)   cleaning (customers, sites, jobs, schedules ...)
Every row keeps its number (id), so the Project app still points at the right quotations.

Run  import_users  FIRST (the cleaning jobs say WHO did them; people are matched by username).
Where the data is:  a db.sqlite3 file or the live Postgres address of each old site (read only - the old sites are never changed):
    py manage.py import_data --dry-run --quotation "postgresql://..." --materials "postgresql://..." --cleaning "postgresql://..."
Defaults are the db.sqlite3 files in the three old folders on the Desktop.
--dry-run   do everything, print the counts, then undo it (look first!)
--replace   empty the tables of an app first when the new site already has rows there (otherwise such an app is skipped, never mixed).
"""
import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from portal.management.commands.import_users import _rows

SOURCES = (("quotation", "quotations"), ("materials", "store"), ("cleaning", "cleaning"))


def order_by_foreign_keys(models):
    """Models that others point to come first."""
    done, left = [], list(models)
    while left:
        progressed = False
        for model in list(left):
            needs = {f.related_model for f in model._meta.concrete_fields if f.is_relation and f.related_model in left and f.related_model is not model}
            if not needs:
                done.append(model)
                left.remove(model)
                progressed = True
        if not progressed:
            done.extend(left)
            break
    return done


class Command(BaseCommand):
    help = "Copies the data of the three old websites into this site."

    def add_arguments(self, parser):
        base = Path(settings.BASE_DIR).parent
        parser.add_argument("--quotation", default=str(base / "quotation_pwa" / "db.sqlite3"))
        parser.add_argument("--materials", default=str(base / "materials_site" / "db.sqlite3"))
        parser.add_argument("--cleaning", default=str(base / "SolarCleaningManager" / "db.sqlite3"))
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--replace", action="store_true")

    def handle(self, *args, **options):
        User = get_user_model()
        new_users = {u.username.lower(): u.pk for u in User.objects.all()}
        summary = []
        try:
            with transaction.atomic():
                for label, app_label in SOURCES:
                    self.copy_app(label, app_label, options, new_users, summary)
                if options["dry_run"]:
                    raise _DryRun()
        except _DryRun:
            pass
        self.stdout.write("\n%-12s %-28s %s" % ("app", "table", "rows"))
        for app_label, name, count, note in summary:
            self.stdout.write("%-12s %-28s %s %s" % (app_label, name, count, note))
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was saved."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone. Open the site and check a few quotations, customers and jobs."))

    def copy_app(self, label, app_label, options, new_users, summary):
        source = options[label]
        is_url = source.startswith(("postgres://", "postgresql://"))
        if not is_url and not Path(source).exists():
            self.stdout.write("%-10s no database at %s: skipped" % (label, source))
            return
        models = order_by_foreign_keys(list(apps.get_app_config(app_label).get_models()))
        existing = sum(m.objects.count() for m in models)
        if existing and not options["replace"]:
            self.stdout.write(self.style.WARNING("%-10s the new site already has %d rows in %s: skipped (use --replace to empty them first)" % (label, existing, app_label)))
            return
        try:
            conn, query = _rows(source)
        except Exception as error:
            raise CommandError("%s: could not open %s (%s)" % (label, source, error))
        try:
            old_user_names = {}
            if any(f.related_model is get_user_model() for m in models for f in m._meta.concrete_fields if f.is_relation):
                old_user_names = {r["id"]: r["username"] for r in query("SELECT id, username FROM auth_user")}
            if options["replace"]:
                for model in reversed(models):
                    model.objects.all().delete()
            for model in models:
                table = model._meta.db_table
                try:
                    rows = query('SELECT * FROM "%s"' % table)
                except Exception as error:
                    summary.append((app_label, table, 0, "(table not in the old database: %s)" % str(error).splitlines()[0][:60]))
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    continue
                objects, lost_users = [], 0
                for row in rows:
                    values = {}
                    for field in model._meta.concrete_fields:
                        if field.column not in row:
                            continue                          # a column the old database did not have: the default is used
                        value = row[field.column]
                        if value is not None and field.is_relation and field.related_model is get_user_model():
                            username = old_user_names.get(value, "")
                            value = new_users.get(username.lower())
                            if value is None:
                                lost_users += 1
                        elif value is not None:
                            value = field.to_python(value)
                            if isinstance(value, datetime.datetime) and timezone.is_naive(value):
                                value = timezone.make_aware(value, datetime.timezone.utc)      # SQLite keeps times in UTC
                        values[field.attname] = value
                    objects.append(model(**values))
                # keep the old "created / updated" times: switch the automatic stamping off while copying
                stamped = [(f, f.auto_now, f.auto_now_add) for f in model._meta.concrete_fields if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False)]
                for f, _, _ in stamped:
                    f.auto_now = f.auto_now_add = False
                try:
                    model.objects.bulk_create(objects, batch_size=500)
                finally:
                    for f, a, b in stamped:
                        f.auto_now, f.auto_now_add = a, b
                note = "(%d jobs / schedules had a person who is not in the new site: left empty)" % lost_users if lost_users else ""
                summary.append((app_label, table, len(objects), note))
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    for sql in connection.ops.sequence_reset_sql(no_style(), models):
                        cursor.execute(sql)
        finally:
            conn.close()


class _DryRun(Exception):
    pass
