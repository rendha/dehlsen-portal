"""Bring the current vendor tracker (vendor_invoice_tracker.xlsx) into Accounts.

  python manage.py import_vendor_excel --file C:\\path\\vendor_invoice_tracker.xlsx --dry-run     (only shows what it would do)
  python manage.py import_vendor_excel --file C:\\path\\vendor_invoice_tracker.xlsx               (imports)

How each row of the Purchase Register is treated (a proforma is never counted as owed):
  * material marked "Yes" received, or the row is paid in full  -> an INVOICE (counted as owed until paid)
  * everything else (no delivery recorded, not fully paid)     -> a PROFORMA (a request); money already paid on it is an ADVANCE
Things the Excel gets wrong are fixed in the import and marked "To confirm" so that Accounts can check them:
  * a payment larger than its row paid by credit card  -> the extra is a card charge, not an overpayment
  * a payment larger than its row (not a card)           -> the extra is moved to that vendor's oldest unpaid row
  * a row without a PI date  -> the entry date is used;  a row with a payment but no amount  -> amount 0
Imports only into an EMPTY Accounts section.  Everything is saved in one go (all or nothing)."""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from finance.models import Invoice, Payment, Proforma, Vendor

ZERO = Decimal("0")


def D(x):
    try:
        return Decimal(str(x)).quantize(Decimal("0.01")) if x not in (None, "") else ZERO
    except Exception:
        return ZERO


def S(x):
    if x is None:
        return ""
    if isinstance(x, float) and x == int(x):
        x = int(x)
    return " ".join(str(x).split())


def day(x):
    if isinstance(x, datetime.datetime):
        return x.date()
    return x if isinstance(x, datetime.date) else None


class Command(BaseCommand):
    help = "Import the vendor tracker Excel into Accounts."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("Run:  pip install openpyxl   and try again.")
        if Vendor.objects.exists() or Invoice.objects.exists() or Proforma.objects.exists() or Payment.objects.exists():
            raise CommandError("Accounts already has data. The import is only for an empty Accounts section, so nothing was imported.")
        wb = openpyxl.load_workbook(o["file"], data_only=True)
        if "Purchase Register" not in wb.sheetnames:
            raise CommandError("This does not look like the vendor tracker (no 'Purchase Register' sheet).")

        vendors = {}
        if "Vendors" in wb.sheetnames:
            for r in wb["Vendors"].iter_rows(min_row=6, values_only=True):
                name = S(r[1])
                if name:
                    vendors[name.lower()] = {"name": name, "credit": int(D(r[2])), "contact": S(r[4]), "phone": S(r[5]), "gst": S(r[6])}

        rows = []
        for n, r in enumerate(wb["Purchase Register"].iter_rows(min_row=6, max_row=505, values_only=True), start=6):
            r = list(r) + [None] * 26
            vendor, amount, paid = S(r[2]), D(r[10]), D(r[13])
            if not vendor or not (amount or paid or S(r[9])):
                continue
            entry, pi_date = day(r[1]), day(r[4])
            notes = []
            if pi_date is None:
                notes.append("No PI date in the Excel; the entry date was used.")
            rows.append(dict(row=n, vendor=vendor, number=S(r[3]), date=pi_date or entry or datetime.date.today(), company=S(r[5]) or "Dehlsen",
                             ptype=S(r[6]), delivery=S(r[7]) or "Godown", customer=S(r[8]), desc=S(r[9]), amount=amount, credit=int(D(r[11])),
                             paid=paid, paid_on=day(r[14]), mode=S(r[15]), ref=S(r[16]), received=S(r[21]).lower() == "yes", link=S(r[22]),
                             remarks=S(r[23]), notes=notes, fee=ZERO, pay_notes=[]))

        # fix the overpayments
        for x in rows:
            if x["paid"] > x["amount"] > 0:
                extra = x["paid"] - x["amount"]
                if x["mode"] == "Credit Card":
                    x["fee"] = extra
                    x["pay_notes"].append("Paid %s on a bill of %s with a credit card: the extra %s is treated as a card charge. Confirm." % (x["paid"], x["amount"], extra))
                    continue
                target = next((y for y in rows if y is not x and y["vendor"].lower() == x["vendor"].lower() and y["paid"] == 0 and y["amount"] >= extra), None)
                if target:
                    x["paid"] -= extra
                    target["paid"], target["paid_on"], target["mode"] = extra, x["paid_on"], x["mode"]
                    why = "One payment of %s on %s covered two bills. It was split: %s here and %s on the other bill. Confirm." % (x["paid"] + extra, x["paid_on"], x["paid"], extra)
                    x["pay_notes"].append(why)
                    target["pay_notes"].append(why)
                    target["notes"].append("Marked paid by the split of one payment. Confirm.")
                else:
                    x["notes"].append("Paid %s on a bill of %s (more than the bill). Confirm." % (x["paid"], x["amount"]))
            elif x["paid"] > 0 and x["amount"] == 0:
                x["notes"].append("A payment of %s is recorded but the amount of the bill is blank in the Excel. Add the amount." % x["paid"])
            if x["number"] == "1000574068":
                x["notes"].append("The older tracker sheet shows this invoice as 61,320 (Satheesh + Sijila); this register has %s. Check the vendor's invoice." % x["amount"])

        for x in rows:
            fully_paid = x["amount"] > 0 and x["paid"] >= x["amount"]
            x["kind"] = "invoice" if (x["received"] or fully_paid) else "proforma"

        self.stdout.write("%-4s %-20s %-9s %12s %12s  %s" % ("row", "vendor", "becomes", "amount", "paid", "note"))
        owed = adv = ZERO
        for x in rows:
            bal = x["amount"] - x["paid"] + x["fee"] * 0
            self.stdout.write("%-4s %-20s %-9s %12s %12s  %s" % (x["row"], x["vendor"][:20], x["kind"], x["amount"], x["paid"], " ".join(x["notes"] + x["pay_notes"])[:70]))
            if x["kind"] == "invoice":
                owed += max(x["amount"] - x["paid"], ZERO)
            else:
                adv += x["paid"]
        self.stdout.write("Invoices still to pay: %s  |  advances with vendors (not owed): %s  |  proformas: %d  |  invoices: %d"
                          % (owed, adv, sum(1 for x in rows if x["kind"] == "proforma"), sum(1 for x in rows if x["kind"] == "invoice")))
        if o["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: nothing saved."))
            return

        with transaction.atomic():
            vmap = {}
            for key, v in vendors.items():
                vmap[key] = Vendor.objects.create(name=v["name"], credit_days=v["credit"], contact=v["contact"], phone=v["phone"], gst_no=v["gst"])
            for x in rows:
                key = x["vendor"].lower()
                if key not in vmap:
                    vmap[key] = Vendor.objects.create(name=x["vendor"], credit_days=x["credit"])
                v = vmap[key]
                common = dict(vendor=v, number=x["number"], date=x["date"], company=x["company"] if x["company"] in ("Dehlsen", "Reed") else "Dehlsen",
                              delivery_to=x["delivery"] if x["delivery"] in ("Godown", "Customer Site") else "Godown", customer_name=x["customer"],
                              description=x["desc"], pdf_link=x["link"], check_note=" ".join(x["notes"])[:300])
                pay = None
                if x["kind"] == "invoice":
                    inv = Invoice.objects.create(amount=x["amount"], credit_days=0 if x["ptype"] == "Cash" else x["credit"], material_received=x["received"],
                                                 approved=True, remarks=x["remarks"], **common)
                    if x["paid"] > 0:
                        Payment.objects.create(vendor=v, invoice=inv, paid_on=x["paid_on"] or x["date"], amount=x["paid"] + x["fee"], fee=x["fee"],
                                               mode=x["mode"], reference=x["ref"], check_note=" ".join(x["pay_notes"])[:300])
                else:
                    pf = Proforma.objects.create(amount=x["amount"], status=Proforma.APPROVED,
                                                 status_note="Imported from the Excel. No invoice or delivery was recorded, so it is not counted as owed. If the material has come, press 'Vendor's invoice has come'.", **common)
                    if x["paid"] > 0:
                        Payment.objects.create(vendor=v, proforma=pf, paid_on=x["paid_on"] or x["date"], amount=x["paid"], mode=x["mode"], reference=x["ref"],
                                               check_note=" ".join(x["pay_notes"])[:300])
        self.stdout.write(self.style.SUCCESS("Imported %d vendors and %d rows." % (Vendor.objects.count(), len(rows))))
