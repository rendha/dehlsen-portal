"""Load the payment sheet's projects: python manage.py import_collections [file.json]
Each project gets its stage payments as history entries (marked "from sheet").  Safe to run again: the sheet's entries are rebuilt, and any payment
entered in the portal is kept and still counted."""
import datetime
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Sum

from portal.models import Collection, Payment


class Command(BaseCommand):
    help = "Load the payment collection sheet into the portal."

    def add_arguments(self, parser):
        parser.add_argument("file", nargs="?", default=str(Path(__file__).resolve().parents[2] / "data" / "collections_seed.json"))

    def handle(self, *args, **options):
        with open(options["file"], encoding="utf-8") as f:
            rows = json.load(f)
        made = updated = 0
        for r in rows:
            pid = r.pop("project_id")
            pays = r.pop("payments", [])
            sheet_total = Decimal(str(r.pop("received")))
            c, new = Collection.objects.update_or_create(project_id=pid, defaults=r)
            made += new
            updated += not new
            c.payments.filter(from_sheet=True).delete()
            for p in pays:
                Payment.objects.create(collection=c, amount=Decimal(str(p["amount"])), stage=p["stage"], from_sheet=True,
                                       date=datetime.date.fromisoformat(p["date"]) if p.get("date") else None,
                                       note="Adjustment from sheet" if p.get("adjust") else "From sheet")
            portal_paid = c.payments.filter(from_sheet=False).aggregate(t=Sum("amount"))["t"] or Decimal(0)
            c.received = sheet_total + portal_paid
            c.save(update_fields=["received"])
        self.stdout.write("Collections: %d added, %d updated." % (made, updated))
