"""python manage.py add_adani_625 [--dry-run]  -  adds the Adani TOPCON DCR 625 W panel at Rs 26 per watt to the Panel options.
Only this one panel is added; the Adani 630 W (Rs 27.50) and every other panel are not touched.  Safe to run twice: if it is already there nothing is added."""
from decimal import Decimal

from django.core.management.base import BaseCommand

from quotations.models import PanelOption


class Command(BaseCommand):
    help = "Add the Adani TOPCON DCR 625 W panel at Rs 26 per watt."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        found = PanelOption.objects.filter(company__iexact="Adani", panel_type__iexact="TOPCON", dcr_status="dcr", wattage=625)
        if found.exists():
            p = found.first()
            self.stdout.write("Already there: %s at Rs %s per watt (active: %s). Nothing changed." % (p, p.rate_per_watt, p.is_active))
            return
        if o["dry_run"]:
            self.stdout.write("Would add: Adani TOPCON DCR 625 W at Rs 26.00 per watt. Nothing saved (dry run).")
            return
        p = PanelOption.objects.create(company="Adani", panel_type="TOPCON", dcr_status="dcr", wattage=Decimal("625"),
                                       rate_per_watt=Decimal("26"), tax_percent=Decimal("2"), is_active=True)
        self.stdout.write(self.style.SUCCESS("Added: %s at Rs %s per watt." % (p, p.rate_per_watt)))
