"""py manage.py fix_master_ids [--dry-run]  -  one-time fix: gives four customers the project id the Project Master workbook gives them.

  FEBINA P P         DH26-27/151 -> DH26-27/153   (her payment row follows)
  JAYARAJAN          DH26-27/152 -> DH26-27/155   (JAYARAJAN T P; his payment row follows; phone/address/map/kW/consumer no from the workbook)
  SATHEESH KUMAR P K (no id)     -> DH26-27/151
  PRAMOD KUMAR P     (no id)     -> DH26-27/152
The old holders are moved first, then the ids are given.  Phone, address, map link, kW, consumer no and booking date of these four are set from the workbook."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import compact, _date
from portal.models import Collection, ProjectWork

MOVES = [("FEBINA P P", "DH26-27/151", "DH26-27/153"), ("JAYARAJAN", "DH26-27/152", "DH26-27/155"),
         ("SATHEESH KUMAR P K", "", "DH26-27/151"), ("PRAMOD KUMAR P", "", "DH26-27/152")]


class Command(BaseCommand):
    help = "Give FEBINA, JAYARAJAN, SATHEESH KUMAR and PRAMOD KUMAR the project ids of the Project Master workbook."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        data = json.loads((Path(__file__).resolve().parents[2] / "data" / "master_seed.json").read_text(encoding="utf-8"))
        found = []
        for name, old, new in MOVES:
            hits = [w for w in ProjectWork.objects.filter(project_id=old) if compact(w.name) == compact(name)]
            if len(hits) != 1:
                self.stdout.write(self.style.ERROR("skip %s (%s): found %d projects, expected 1 - nothing changed for it" % (name, old or "no id", len(hits))))
                continue
            found.append((hits[0], old, new))
        for w, old, new in found:
            r = data[new]
            self.stdout.write("%s: %s -> %s   (phone %s -> %s, kW %s -> %s, consumer %s -> %s)" % (
                w.name, old or "no id", new, w.phone, r.get("phone") or w.phone, w.kw, r.get("kw") or w.kw, w.kseb_consumer_no, r.get("consumer_no") or ""))
            if dry:
                continue
            w.project_id = new
            col = w.collection
            if col and old and col.project_id == old:
                col.project_id = new
                col.save()
            if new == "DH26-27/155":
                w.name, w.name_key = r["name"][:200], r["name"][:200].lower()
            for f in ("phone", "site_address", "map_link", "kw"):
                if r.get(f):
                    setattr(w, f, r[f])
            w.kseb_consumer_no = r.get("consumer_no") or ""
            if r.get("booking_date"):
                w.booking_date = _date(r["booking_date"])
            w.save()
        self.stdout.write(self.style.SUCCESS("%s %d of %d customers." % ("Would fix" if dry else "Fixed", len(found), len(MOVES))))
