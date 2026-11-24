"""Add the opening vendor balances (24 Nov 2026 list) as unpaid payables, with the right company.

    python manage.py import_payables --dry-run     (shows what it would do, changes nothing)
    python manage.py import_payables               (does it)

Skipped on purpose: ALPHADEX POWER and GREAT LEAP (not wanted), BUILDTECH and SM TECH (no amount given).
Each row becomes one vendor invoice: invoice no. blank, credit days 0, dated 24 Nov 2026.
Safe to run again: a row that already exists (same vendor, amount, description) is not added twice;
if its company is different from this list, only the company is corrected.
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import Invoice, Vendor

NOTE = "Opening balance - list of 24 Nov 2026"
ROWS = [
    ("EXCEL ERTHING", "50266", "Reed"),
    ("AXIS POWER", "331651", "Reed"),
    ("VIBGYOR", "225335", "Reed"),
    ("VENKATESWARA", "124861", "Dehlsen"),
    ("PIPES INDIA", "9782", "Dehlsen"),
    ("KIAH ENERGIED", "2464884", "Reed"),
    ("SUNSPECTRUM", "227535", "Reed"),
    ("PONIARD", "71620", "Dehlsen"),
    ("SS FASTENERS", "16344", "Dehlsen"),
    ("VIGNESWARA", "47850", "Dehlsen"),
]


class Command(BaseCommand):
    help = "Add the opening vendor balances as payables."

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *a, **o):
        dry, today, total = o["dry_run"], datetime.date(2026, 11, 24), Decimal("0")
        for name, amt, company in ROWS:
            amt = Decimal(amt)
            v = Vendor.objects.filter(name__iexact=name).first()
            made = ""
            if v is None:
                made = " (new vendor)"
                if not dry:
                    v = Vendor.objects.create(name=name)
            inv = Invoice.objects.filter(vendor=v, amount=amt, description=NOTE).first() if v is not None else None
            if inv is not None:
                if inv.company != company:
                    self.stdout.write("%-6s %-16s %10s  company %s -> %s" % ("would" if dry else "fix", name, amt, inv.company, company))
                    if not dry:
                        inv.company = company
                        inv.save(update_fields=["company"])
                else:
                    self.stdout.write("skip   %-16s %10s  already there (%s)" % (name, amt, company))
                continue
            self.stdout.write("%-6s %-16s %10s  %s%s" % ("would" if dry else "add", name, amt, company, made))
            total += amt
            if not dry:
                Invoice.objects.create(vendor=v, date=today, company=company, amount=amt, credit_days=0, description=NOTE)
        self.stdout.write("%s new total: %s" % ("Would add" if dry else "Added", total))
        if dry:
            self.stdout.write("Dry run - nothing changed.")
