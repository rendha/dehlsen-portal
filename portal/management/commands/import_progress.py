"""Load the project progress of every customer from portal/data/progress_seed.json (made from the Daily Project Update sheet).
Safe to run again: a customer already there is updated only if --overwrite is given.   python manage.py import_progress"""
import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.models import Collection, ProjectWork
from portal.project_work import match_collection

SEED = Path(__file__).resolve().parents[2] / "data" / "progress_seed.json"


def _date(v):
    try:
        return datetime.date.fromisoformat(v) if v else None
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Import the project progress rows (stage ticks, commissioning, handover) and link them to the payment projects."

    def add_arguments(self, parser):
        parser.add_argument("--overwrite", action="store_true", help="Also overwrite the ticks of customers that are already loaded.")

    def handle(self, *args, **opts):
        from quotations import dashboard_stats as stats
        rows = json.loads(SEED.read_text(encoding="utf-8"))
        collections = list(Collection.objects.all())
        existing = {w.name_key: w for w in ProjectWork.objects.all()}
        added = updated = linked = 0
        unlinked = []
        for d in rows:
            d = dict(d)
            key = stats.name_key(d["name"])
            d["commission_date"] = _date(d.get("commission_date"))
            d["booking_date"] = _date(d.get("booking_date"))
            fields = {f.name for f in ProjectWork._meta.fields}
            data = {k: v for k, v in d.items() if k in fields}
            w = existing.get(key)
            if w is None:
                w = ProjectWork(name_key=key, **data)
                added += 1
            elif opts["overwrite"]:
                for k, v in data.items():
                    setattr(w, k, v)
                updated += 1
            else:
                continue
            c = match_collection(w.name, collections)
            if c is not None:
                w.collection, w.project_id = c, c.project_id
                linked += 1
            elif not w.collection_id:
                unlinked.append(w.name)
            w.save()
            existing[key] = w
        self.stdout.write("Project progress: %d added, %d updated, %d linked to a payment project." % (added, updated, linked))
        if unlinked:
            self.stdout.write("Not linked to a payment project (%d, usually old customers): %s ..." % (len(unlinked), ", ".join(unlinked[:12])))
