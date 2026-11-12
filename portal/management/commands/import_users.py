"""py manage.py import_users  -  copies the people (username, name, PASSWORD, owner/employee setting, groups) from your three old apps,
so everybody signs in to the one site with the login they already have.

It reads the  db.sqlite3  files of the old folders.  Defaults (next to this project on the Desktop):
    ../SolarCleaningManager/db.sqlite3   ../materials_site/db.sqlite3   ../quotation_pwa/db.sqlite3
Other places:  --cleaning PATH  --materials PATH  --quotation PATH      Look first, change nothing:  --dry-run
The same username in several apps becomes ONE account: its groups are added together; is_staff / is_superuser are kept if any app has them;
the password of the first app that has the person is used (order: cleaning, materials, quotation).  Different passwords are listed.
"""
import datetime
import sqlite3
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

FIELDS = ["username", "password", "first_name", "last_name", "email", "is_staff", "is_superuser", "is_active", "date_joined", "last_login"]


def read_source(path):
    """-> ({username: row dict}, {username: [group names]}) from an old Django SQLite database."""
    connection = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        users = {}
        ids = {}
        for row in connection.execute("SELECT * FROM auth_user"):
            data = dict(row)
            users[data["username"]] = data
            ids[data["id"]] = data["username"]
        groups = {}
        try:
            names = {r["id"]: r["name"] for r in connection.execute("SELECT id, name FROM auth_group")}
            for r in connection.execute("SELECT user_id, group_id FROM auth_user_groups"):
                if r["user_id"] in ids and r["group_id"] in names:
                    groups.setdefault(ids[r["user_id"]], []).append(names[r["group_id"]])
        except sqlite3.Error:
            pass
        return users, groups
    finally:
        connection.close()


def as_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is not None and timezone.is_naive(value):
        value = timezone.make_aware(value, datetime.timezone.utc)
    return value


class Command(BaseCommand):
    help = "Copies the users (with their passwords and groups) from the old apps' SQLite databases."

    def add_arguments(self, parser):
        base = Path(settings.BASE_DIR).parent
        parser.add_argument("--cleaning", default=str(base / "SolarCleaningManager" / "db.sqlite3"))
        parser.add_argument("--materials", default=str(base / "materials_site" / "db.sqlite3"))
        parser.add_argument("--quotation", default=str(base / "quotation_pwa" / "db.sqlite3"))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        merged, groups_of, passwords = {}, {}, {}
        for label in ("cleaning", "materials", "quotation"):
            path = Path(options[label])
            if not path.exists():
                self.stdout.write("%-10s no database file at %s (skipped)" % (label, path))
                continue
            try:
                users, groups = read_source(path)
            except sqlite3.Error as error:
                self.stdout.write(self.style.WARNING("%-10s could not be read (%s)" % (label, error)))
                continue
            self.stdout.write("%-10s %d user(s)" % (label, len(users)))
            for name, row in users.items():
                key = name.lower()
                if key not in merged:
                    merged[key] = dict(row)
                    passwords[key] = {label: row["password"]}
                else:
                    first = merged[key]
                    for flag in ("is_staff", "is_superuser"):
                        first[flag] = bool(first[flag]) or bool(row[flag])
                    first["is_active"] = bool(first["is_active"]) or bool(row["is_active"])
                    passwords[key][label] = row["password"]
                groups_of.setdefault(key, set()).update(groups.get(name, []))

        differing = [merged[k]["username"] for k, p in passwords.items() if len(set(p.values())) > 1]
        self.stdout.write("\n%d different person(s) in all." % len(merged))
        if differing:
            self.stdout.write(self.style.WARNING("Same username but a DIFFERENT password in two apps (the first app's password is used): " + ", ".join(sorted(differing))))
        if options["dry_run"]:
            for key, row in sorted(merged.items()):
                self.stdout.write("  %-20s staff=%s groups=%s" % (row["username"], bool(row["is_staff"]), ", ".join(sorted(groups_of.get(key, []))) or "-"))
            self.stdout.write("Dry run: nothing was changed.")
            return

        User = get_user_model()
        created = updated = 0
        with transaction.atomic():
            for key, row in merged.items():
                existing = User.objects.filter(username__iexact=row["username"]).first()
                values = {f: row.get(f) for f in FIELDS if f in row}
                for flag in ("is_staff", "is_superuser", "is_active"):
                    values[flag] = bool(values.get(flag))
                values["date_joined"] = as_datetime(values.get("date_joined")) or timezone.now()
                values["last_login"] = as_datetime(values.get("last_login"))
                if existing:
                    # keep what is already in the new site (a password set here, for example); only add power and missing details
                    existing.is_staff = existing.is_staff or values["is_staff"]
                    existing.is_superuser = existing.is_superuser or values["is_superuser"]
                    for f in ("first_name", "last_name", "email"):
                        if not getattr(existing, f) and values.get(f):
                            setattr(existing, f, values[f])
                    existing.save()
                    user = existing
                    updated += 1
                else:
                    user = User.objects.create(**values)
                    created += 1
                for name in sorted(groups_of.get(key, [])):
                    group, _ = Group.objects.get_or_create(name=name)
                    user.groups.add(group)
        self.stdout.write(self.style.SUCCESS("Done: %d new account(s), %d already there (kept)." % (created, updated)))
