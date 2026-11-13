"""Make payment records for the quotations already confirmed as customers: python manage.py sync_collections [--apply]
Without --apply it only lists what it WOULD add (so a client whose name is spelled differently in the sheet is not added twice)."""
from django.core.management.base import BaseCommand

from portal import payments
from portal.models import Collection
from quotations.models import Quotation


class Command(BaseCommand):
    help = "Create payment records for confirmed customers that have none."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        new = []
        for q in Quotation.objects.filter(is_customer=True).order_by("date"):
            if payments._find(q) is None:
                new.append(q)
        for q in new:
            self.stdout.write("%s | %s | for %s | Rs %s" % (q.offer_no, q.business_name or q.customer_name, q.customer_name, q.final_quotation_price))
            if options["apply"]:
                payments.sync_quotation(q)
        self.stdout.write("%d %s." % (len(new), "added" if options["apply"] else "would be added (run with --apply)"))
