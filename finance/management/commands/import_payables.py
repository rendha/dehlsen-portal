"""Add the opening vendor balances (24 Nov 2026 list) as unpaid payables.

    python manage.py import_payables --dry-run     (shows what it would do, changes nothing)
    python manage.py import_payables               (does it)

Skipped on purpose: ALPHADEX POWER and GREAT LEAP (not wanted), BUILDTECH (no amount given).
Each row becomes one vendor invoice: company Dehlsen (edit later), invoice no. blank, credit days 0.
Safe to run twice: a row that already exists (same vendor, same amount, same description) is skipped.
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import Invoice, Vendor

NOTE = "Opening balance - list of 24 Nov 2026"
ROWS = [
    ("EXCEL ERTHING", "50266"),
    ("AXIS POWER", "331651"),
    ("VIBGYOR", "225335"),
    ("VENKATESWARA", "124861"),
    ("PIPES INDIA", "9782"),
    ("KIAH ENERGIED", "2464884"),
    ("SUNSPECTRUM", "227535"),
    ("PONIARD", "71620"),
    ("SS FASTENERS", "16344"),
]


class Command(BaseCommand):
    help = "Add the opening vendor balances as payables."

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *a, **o):
        dry, today, total = o["dry_run"], datetime.date(2026, 11, 24), Decimal("0")
        for name, amt in ROWS:
            amt = Decimal(amt)
            v = Vendor.objects.filter(name__iexact=name).first()
            made = ""
            if v is None:
                made = " (new vendor)"
                if not dry:
                    v = Vendor.objects.create(name=name)
            if v is not None and Invoice.objects.filter(vendor=v, amount=amt, description=NOTE).exists():
                self.stdout.write("skip   %-16s %10s  already added" % (name, amt))
                continue
            self.stdout.write("%-6s %-16s %10s%s" % ("would" if dry else "add", name, amt, made))
            total += amt
            if not dry:
                Invoice.objects.create(vendor=v, date=today, company="Dehlsen", amount=amt, credit_days=0, description=NOTE)
        self.stdout.write("%s total: %s" % ("Would add" if dry else "Added", total))
        if dry:
            self.stdout.write("Dry run - nothing changed.")
