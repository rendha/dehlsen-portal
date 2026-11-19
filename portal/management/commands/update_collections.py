"""Bring the PAYMENT COLLECTION sheet (Projects tab) into the portal's Collections / Receivables.

  python manage.py update_collections --file PAYMENT_COLLECTION_DATA.xlsx --dry-run     (shows what it would do, saves nothing)
  python manage.py update_collections --file PAYMENT_COLLECTION_DATA.xlsx               (does it)

  * a project that is not in the portal yet       -> added, with each stage payment of the sheet as a confirmed payment
  * a project already there, the sheet shows MORE received than the portal -> the difference is added as one payment "from sheet"
  * a project already there, the portal shows MORE than the sheet           -> only reported (payments typed in the portal); nothing is changed
  * deal value, discount and the other details of an existing project are refreshed from the sheet
  * empty rows (a Project ID with no customer) are ignored.  Safe to run again: it only adds what is missing."""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from portal.models import Collection, Payment

STAGES = [("Stage 1: Advance", "advance"), ("Stage 2: Material Dispatch", "material"), ("Stage 3: Installation", "installation"),
          ("Stage 4: Handover", "handover"), ("Extra Payment 5", "other"), ("Extra Payment 6", "other")]


def D(x):
    try:
        return Decimal(str(x)).quantize(Decimal("0.01")) if x not in (None, "") else Decimal("0")
    except Exception:
        return Decimal("0")


def S(x):
    return " ".join(str(x).split()) if x not in (None, "") else ""


def day(x):
    if isinstance(x, datetime.datetime):
        return x.date()
    return x if isinstance(x, datetime.date) else None


class Command(BaseCommand):
    help = "Update Collections (receivables) from the payment collection sheet."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("pip install openpyxl first")
        wb = openpyxl.load_workbook(opts["file"], data_only=True)
        if "Projects" not in wb.sheetnames:
            raise CommandError("The file has no 'Projects' sheet.")
        ws = wb["Projects"]
        head = None
        for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
            if row and row[0] == "Project ID":
                head = [S(c) for c in row]
                break
        if head is None:
            raise CommandError("Could not find the header row (Project ID ...).")
        col = {h: i for i, h in enumerate(head) if h}

        def get(r, name):
            i = col.get(name)
            return r[i] if i is not None and i < len(r) else None

        added = refreshed = topped = 0
        lines, over = [], []
        with transaction.atomic():
            for r in ws.iter_rows(min_row=4, values_only=True):
                pid = S(get(r, "Project ID"))
                name = S(get(r, "Customer Name"))
                if not pid.startswith("DH") or not name:
                    continue
                deal, disc = D(get(r, "Deal Value (₹)")), D(get(r, "Discount (₹)"))
                pays = []
                for label, stage in STAGES:
                    amt = D(get(r, label + " (₹)"))
                    if amt > 0:
                        pays.append((stage, day(get(r, label + " Date")), amt))
                total = sum((p[2] for p in pays), Decimal("0"))
                fields = dict(
                    booking_date=day(get(r, "Booking Date")), customer=name[:150], region=S(get(r, "Region"))[:60], sales_name=S(get(r, "Sales In-Charge"))[:60],
                    kw=D(get(r, "Capacity (kW)")), deal_value=deal, discount=disc, net_value=deal - disc, expected_gp=D(get(r, "Expected GP (₹)")),
                    incentive_category=S(get(r, "Incentive Category"))[:5], site_address=S(get(r, "Site Address")), remarks=S(get(r, "Remarks")),
                    segment=S(get(r, "Segment"))[:20], system_type=S(get(r, "System Type"))[:20], almm=S(get(r, "ALMM"))[:10], panel=S(get(r, "Panel"))[:60],
                    inverter=S(get(r, "Inverter"))[:60], work_status=S(get(r, "Work Status"))[:60], phone=S(get(r, "Phone"))[:30])
                c = Collection.objects.filter(project_id=pid).first()
                if c is None:
                    added += 1
                    lines.append("   NEW      %-13s %-32s net %10s  received %10s" % (pid, name[:32], fields["net_value"], total))
                    if not opts["dry_run"]:
                        c = Collection.objects.create(project_id=pid, received=total, **fields)
                        for stage, d, amt in pays:
                            Payment.objects.create(collection=c, amount=amt, date=d, stage=stage, note="from the payment sheet", from_sheet=True, confirmed=True)
                    continue
                gap = total - c.received
                changed = [k for k in ("net_value", "deal_value", "discount", "kw") if getattr(c, k) != fields[k]]
                if gap > Decimal("0.5"):
                    topped += 1
                    lines.append("   MORE IN SHEET  %-13s %-32s portal %10s -> sheet %10s  (adds %s)" % (pid, c.customer[:32], c.received, total, gap))
                    if not opts["dry_run"]:
                        latest = max((p[1] for p in pays if p[1]), default=None)
                        Payment.objects.create(collection=c, amount=gap, date=latest, stage="other", note="added from the payment sheet update", from_sheet=True, confirmed=True)
                        fields["received"] = c.received + gap
                elif gap < Decimal("-0.5"):
                    over.append("   PORTAL HAS MORE %-13s %-32s portal %10s, sheet %10s (not changed)" % (pid, c.customer[:32], c.received, total))
                if changed:
                    refreshed += 1
                if not opts["dry_run"]:
                    for k, v in fields.items():
                        setattr(c, k, v)
                    c.save()
            if opts["dry_run"]:
                transaction.set_rollback(True)
        for l in lines + over:
            self.stdout.write(l)
        self.stdout.write("%s%d new project(s), %d with more money in the sheet, %d refreshed details, %d where the portal has more." % (
            "Dry run, nothing saved: " if opts["dry_run"] else "Done: ", added, topped, refreshed, len(over)))
