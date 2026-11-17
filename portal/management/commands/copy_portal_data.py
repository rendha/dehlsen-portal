"""Copy the portal's own data (leads, tasks, projects, collections, payments, targets, profiles ... and the add-on quotations) from the
old TEST portal database into the database the portal will use from now on.  Only these tables are copied; quotations, rates, cleaning and
store data are NOT touched (they are already newer in the target).

  $env:DATABASE_URL        = the TARGET  (quotation-db, External URL)
  $env:SOURCE_DATABASE_URL = the SOURCE  (the test portal database, External URL)
  python manage.py copy_portal_data --dry-run     (only looks)
  python manage.py copy_portal_data               (copies)

Safe by design: nothing is copied if a target table already has rows; every person is matched by username (the people lists have different
numbers in the two databases); the whole copy is ONE transaction (all or nothing); the source is only read, never changed.
Run `python manage.py migrate` against the target first, so that the portal tables exist.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

EXTRA_TABLES = ["quotations_addonquotation", "quotations_addonitem"]


def _connect(url):
    try:
        import psycopg
        return psycopg.connect(url)
    except ImportError:
        import psycopg2
        return psycopg2.connect(url)


def q(c, sql, params=None):
    c.execute(sql, params or [])
    return c.fetchall()


class Command(BaseCommand):
    help = "Copy the portal's own tables from the old test portal database into the target database."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        url = os.environ.get("SOURCE_DATABASE_URL")
        if not url:
            raise CommandError("Set SOURCE_DATABASE_URL to the External URL of the test portal database first.")
        if connection.vendor != "postgresql":
            raise CommandError("DATABASE_URL must be the quotation-db External URL.")
        src = _connect(url)
        try:
            sc = src.cursor()
            with connection.cursor() as tc:
                self.run(sc, tc, o["dry_run"])
        finally:
            src.close()

    def run(self, sc, tc, dry):
        # ---- which tables
        stables = [r[0] for r in q(sc, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")]
        ttables = {r[0] for r in q(tc, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        todo = []
        for t in stables:
            if not (t.startswith("portal_") or t in EXTRA_TABLES):
                continue
            n = q(sc, 'SELECT count(*) FROM public."%s"' % t)[0][0]
            if n == 0:
                continue
            if t not in ttables:
                raise CommandError("The target has no table %s. Run 'python manage.py migrate' against the target first." % t)
            have = q(tc, 'SELECT count(*) FROM public."%s"' % t)[0][0]
            if have:
                raise CommandError("The target table %s already has %d rows. Nothing was copied. Stop here and ask for help." % (t, have))
            todo.append((t, n))
        if not todo:
            self.stdout.write("Nothing to copy.")
            return

        # ---- people: source id -> target id, by username
        smap = {i: u.lower() for i, u in q(sc, "SELECT id, username FROM auth_user")}
        tmap = {u.lower(): i for i, u in q(tc, "SELECT id, username FROM auth_user")}
        missing = sorted(u for u in smap.values() if u not in tmap)
        idmap = {i: tmap[u] for i, u in smap.items() if u in tmap}
        if missing:
            self.stdout.write(self.style.WARNING("People in the source with no login in the target: %s" % ", ".join(missing)))
        # columns that point to a person (found from the target's own foreign keys)
        fk = q(tc, """SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c
                      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                      WHERE c.contype = 'f' AND c.confrelid = 'public.auth_user'::regclass""")
        usercols = {}
        for tbl, col in fk:
            usercols.setdefault(tbl.replace("public.", "").strip('"'), set()).add(col)

        self.stdout.write("%-34s %8s" % ("table", "rows"))
        plan = []
        for t, n in todo:
            scols = [r[0] for r in q(sc, "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", [t])]
            tinfo = {r[0]: r[1] for r in q(tc, "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", [t])}
            cols = [c for c in scols if c in tinfo]
            drop = [c for c in scols if c not in tinfo]
            rows = q(sc, 'SELECT %s FROM public."%s"' % (", ".join('"%s"' % c for c in cols), t))
            remap = [i for i, c in enumerate(cols) if c in usercols.get(t, set())]
            bad = 0
            for r in rows:
                for i in remap:
                    if r[i] is not None and r[i] not in idmap:
                        bad += 1
            note = ""
            if drop:
                note += "  (columns not in the target, ignored: %s)" % ", ".join(drop)
            if remap:
                note += "  (people matched by username: %s)" % ", ".join(cols[i] for i in remap)
            if bad:
                note += "  !! %d rows point to a person with no login in the target" % bad
            self.stdout.write("%-34s %8d%s" % (t, n, note))
            plan.append((t, cols, tinfo, rows, remap, bad))
        problems = sum(p[5] for p in plan)
        if problems:
            raise CommandError("Some rows point to people who are not in the target (listed above). Nothing was copied. Add those logins first.")
        if dry:
            self.stdout.write(self.style.SUCCESS("Dry run: nothing changed. It is safe to run it without --dry-run."))
            return

        # ---- copy, all or nothing
        with transaction.atomic():
            tc.execute("SET CONSTRAINTS ALL DEFERRED")
            for t, cols, tinfo, rows, remap, _bad in plan:
                ph = ["%s::" + tinfo[c] if tinfo[c] in ("json", "jsonb") else "%s" for c in cols]
                sql = 'INSERT INTO public."%s" (%s) VALUES (%s)' % (t, ", ".join('"%s"' % c for c in cols), ", ".join(ph))
                for r in rows:
                    r = list(r)
                    for i in remap:
                        if r[i] is not None:
                            r[i] = idmap[r[i]]
                    for i, c in enumerate(cols):
                        if isinstance(r[i], (dict, list)):
                            r[i] = json.dumps(r[i])
                    tc.execute(sql, r)
                if "id" in cols:           # the next new row must not reuse a copied number
                    tc.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), (SELECT COALESCE(max(id), 1) FROM public.\"" + t + "\"))", ['public."%s"' % t])
        for t, cols, *_ in plan:
            have = q(tc, 'SELECT count(*) FROM public."%s"' % t)[0][0]
            self.stdout.write("copied %-30s %8d" % (t, have))
        self.stdout.write(self.style.SUCCESS("Done. The portal data is now in the target database. Check the portal, then switch the service."))
