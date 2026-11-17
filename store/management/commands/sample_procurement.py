"""Puts ONE sample customer (with material lines, customer payments, supplier purchases on credit, due dates) into the portal so the Procurement pages can be seen with data.
    python manage.py sample_procurement            add / refresh the sample
    python manage.py sample_procurement --remove   delete the sample again (everything named SAMPLE)"""
import datetime
from decimal import Decimal as D

from django.core.management.base import BaseCommand
from django.utils import timezone

from store.models import Customer, Line, Payment, Purchase, Supplier, SupplierPayment

OFFER = "SAMPLE-001"
PREFIX = "SAMPLE "


def remove():
    Purchase.objects.filter(supplier__name__startswith=PREFIX).delete()
    Supplier.objects.filter(name__startswith=PREFIX).delete()
    Customer.objects.filter(offer_no=OFFER).delete()


class Command(BaseCommand):
    help = "Add (or with --remove, delete) a sample customer for the Procurement pages."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **opts):
        remove()
        if opts["remove"]:
            self.stdout.write("Sample removed.")
            return
        today = timezone.localdate()
        d = lambda n: today + datetime.timedelta(days=n)
        c = Customer.objects.create(offer_no=OFFER, name="SAMPLE Customer (delete me)", person="Sample", phone="9000000000", location="Feroke",
                                    system_size="5", quoted_total=D("345000"), status=Customer.SENT)
        rows = [  # name, make, unit, qty, rate, source, store status
            ("Adani Solar Panel 590W", "Bifacial", "Nos", 10, "14306.25", Line.PURCHASE, Line.DONE),
            ("Deye 5kW Hybrid Inverter", "Deye", "Nos", 1, "62000", Line.PURCHASE, Line.DONE),
            ("DC cable 4 sq mm", "", "m", 60, "48", Line.WAREHOUSE, Line.DONE),
            ("AC cable 4C 6 sq mm", "", "m", 25, "210", Line.WAREHOUSE, Line.DONE),
            ("MC4 connector", "ningbo", "Nos", 8, "40", Line.WAREHOUSE, Line.DONE),
            ("ACDB / DCDB box", "", "Set", 1, "5200", Line.WAREHOUSE, Line.DONE),
            ("Structure (GI) 5 kW", "", "Set", 1, "18500", Line.PURCHASE, Line.PENDING),
            ("Earthing kit", "", "Set", 1, "3800", Line.WAREHOUSE, Line.PENDING),
            ("Lightning arrester", "", "Nos", 1, "2400", Line.PURCHASE, Line.SHORT),
        ]
        for i, (n, mk, u, q, r, src, st) in enumerate(rows):
            Line.objects.create(customer=c, position=i, name=n, make=mk, unit=u, quantity=D(q), rate=D(r), source=src, store_status=st)
        Payment.objects.create(customer=c, amount=D("50000"), paid_on=d(-60), mode=Payment.BANK, note="Advance (sample)")
        Payment.objects.create(customer=c, amount=D("100000"), paid_on=d(-30), mode=Payment.UPI, note="Material payment (sample)")

        adani = Supplier.objects.create(name=PREFIX + "Adani Dealer, Kozhikode")
        deye = Supplier.objects.create(name=PREFIX + "Deye Distributor")
        metro = Supplier.objects.create(name=PREFIX + "Metro Electricals")
        p1 = Purchase.objects.create(supplier=adani, customer=c, description="10 x Adani 590W panels", amount=D("150000"), ordered_on=d(-45),
                                     credit=False, received_on=d(-40), invoice_no="AD-1021")
        SupplierPayment.objects.create(purchase=p1, amount=D("150000"), paid_on=d(-45), mode=Payment.BANK)
        Purchase.objects.create(supplier=deye, customer=c, description="Deye 5kW hybrid inverter", amount=D("60000"), ordered_on=d(-35),
                                credit=True, due_date=d(-3), received_on=d(-30), invoice_no="DY-554")                      # overdue
        p3 = Purchase.objects.create(supplier=metro, customer=c, description="Cables, DB box, earthing", amount=D("20000"), ordered_on=d(-10),
                                     credit=True, due_date=d(5), expected_on=d(2), invoice_no="ME-88")                      # due soon, not delivered
        SupplierPayment.objects.create(purchase=p3, amount=D("5000"), paid_on=d(-9), mode=Payment.CASH, note="Part payment (sample)")
        Purchase.objects.create(supplier=metro, description="Stock: 200 m DC cable (general stock)", amount=D("9600"), ordered_on=d(-2),
                                credit=True, due_date=d(20), expected_on=d(4))
        self.stdout.write("Sample added: open Procurement and the customer 'SAMPLE Customer (delete me)'. Remove it with: python manage.py sample_procurement --remove")
