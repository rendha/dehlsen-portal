"""List (and only if told to, delete) vendor proformas.

    python manage.py clear_proformas              LIST ONLY - nothing is changed
    python manage.py clear_proformas --delete     deletes every proforma  (take a fresh export first!)
    python manage.py clear_proformas --delete --keep-paid    deletes only proformas with no payments on them

Deleting a proforma also deletes the payments entered against it (advance payments).
Invoices made from a proforma are kept; they just lose the link to it.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import Payment, Proforma


class Command(BaseCommand):
    help = "List or delete vendor proformas."

    def add_arguments(self, p):
        p.add_argument("--delete", action="store_true")
        p.add_argument("--keep-paid", action="store_true", help="with --delete: keep proformas that have payments")

    @transaction.atomic
    def handle(self, *a, **o):
        rows = list(Proforma.objects.select_related("vendor").prefetch_related("payments", "invoices"))
        if not rows:
            self.stdout.write("No proformas.")
            return
        total_amt, total_pay, n_pay, doomed = Decimal("0"), Decimal("0"), 0, []
        for pf in rows:
            pays = list(pf.payments.all())
            paid = sum((p.amount for p in pays), Decimal("0"))
            inv = pf.invoices.count()
            self.stdout.write("%-5s %-22s %-8s %-10s %12s  payments:%d (%s)  invoices linked:%d  %s" % (
                pf.pk, pf.vendor.name[:22], pf.company, pf.date, pf.amount, len(pays), paid, inv, pf.status))
            if o["keep_paid"] and pays:
                continue
            doomed.append(pf)
            total_amt += pf.amount
            total_pay += paid
            n_pay += len(pays)
        self.stdout.write("")
        self.stdout.write("%d proformas (Rs %s) %s, with %d payments (Rs %s) attached." % (
            len(doomed), total_amt, "WILL BE DELETED" if o["delete"] else "would be deleted", n_pay, total_pay))
        if not o["delete"]:
            self.stdout.write("LIST ONLY - nothing changed. Add --delete to delete.")
            return
        for pf in doomed:
            pf.delete()
        self.stdout.write("Deleted %d proformas. Payments left in total: %d" % (len(doomed), Payment.objects.count()))
