"""Customers whose confirmed QUOTATION value and the DEAL value in the collections sheet are different, and whether a discount explains it.
READ-ONLY: nothing in the database is changed.  It writes an Excel file.

  $env:DATABASE_URL = the quotation-db External URL      (and a temporary DJANGO_SECRET_KEY, as before)
  python manage.py quote_vs_deal                         -> quote_vs_deal.xlsx in the project folder
  python manage.py quote_vs_deal --out C:\\Users\\sayed\\Desktop\\quote_vs_deal.xlsx

Sheets:  Needs checking  (still two different numbers after the discount) / Explained by discount / Same value / No quotation linked / Summary
Rule:    Quotation value (Q) is compared with the deal value (D) and with the net value (N = D - discount).
         |Q - D| <= tolerance            -> same value
         |Q - N| <= tolerance            -> explained by the discount
         otherwise                       -> needs checking
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from portal.models import Collection, ProjectWork
from quotations.models import Quotation

ZERO = Decimal("0")


def _num(x):
    return Decimal(str(x)) if x not in (None, "") else ZERO


class Command(BaseCommand):
    help = "Excel list of customers whose quotation value and deal value differ (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="quote_vs_deal.xlsx")
        parser.add_argument("--tolerance", type=int, default=100, help="rupees treated as the same (rounding), default 100")

    def handle(self, *args, **o):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            raise CommandError("Run:  pip install openpyxl   and try again.")
        tol = Decimal(o["tolerance"])

        # the quotation of each customer: from the collection itself, else from its project
        quotes = {q.id: q for q in Quotation.objects.all()}
        qid = {}
        for c in Collection.objects.all():
            if c.quotation_id:
                qid[c.id] = c.quotation_id
        for w in ProjectWork.objects.exclude(collection__isnull=True).exclude(quotation_id__isnull=True):
            qid.setdefault(w.collection_id, w.quotation_id)

        needs, explained, same, unlinked = [], [], [], []
        for c in Collection.objects.order_by("project_id"):
            q = quotes.get(qid.get(c.id))
            D, X, N = _num(c.deal_value), _num(c.discount), _num(c.net_value)
            if q is None:
                unlinked.append([c.project_id, c.customer, c.sales_name, float(D), float(X), float(N), float(_num(c.received))])
                continue
            Q = _num(q.final_quotation_price)
            row = [c.project_id, c.customer, c.sales_name, q.offer_no, q.business_name or q.customer_name, float(Q), float(D), float(X), float(N),
                   float(Q - D), float(Q - N), float(_num(c.received))]
            if abs(Q - D) <= tol:
                same.append(row)
            elif abs(Q - N) <= tol:
                explained.append(row)
            else:
                needs.append(row)

        head = ["Project ID", "Customer", "Sales", "Quotation no.", "Quotation customer", "Quotation value", "Deal value", "Discount", "Net value (deal - discount)",
                "Quotation - Deal", "Quotation - Net", "Received"]
        wb = Workbook()
        bold, fill = Font(name="Arial", bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E79")
        money = "#,##0;(#,##0);-"

        def sheet(title, hdr, data, first=False, money_cols=()):
            ws = wb.active if first else wb.create_sheet()
            ws.title = title
            ws.append(hdr)
            for cell in ws[1]:
                cell.font, cell.fill = bold, fill
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            for r in data:
                ws.append(r)
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.font = Font(name="Arial")
                    if cell.column in money_cols:
                        cell.number_format = money
            for i, h in enumerate(hdr, 1):
                ws.column_dimensions[ws.cell(1, i).column_letter].width = 28 if i in (2, 5) else 16
            ws.freeze_panes = "C2"
            return ws

        m = (6, 7, 8, 9, 10, 11, 12)
        sheet("Needs checking", head, needs, True, m)
        sheet("Explained by discount", head, explained, False, m)
        sheet("Same value", head, same, False, m)
        sheet("No quotation linked", ["Project ID", "Customer", "Sales", "Deal value", "Discount", "Net value", "Received"], unlinked, False, (4, 5, 6, 7))
        s = wb.create_sheet("Summary")
        for line in [["Customers in the collections sheet", Collection.objects.count()], ["Same value", len(same)], ["Different, explained by the discount", len(explained)],
                     ["Different, still needs checking", len(needs)], ["No confirmed quotation linked", len(unlinked)], ["Rounding tolerance (Rs)", int(tol)]]:
            s.append(line)
        s.column_dimensions["A"].width = 44
        wb.save(o["out"])
        self.stdout.write(self.style.SUCCESS("Saved %s  | same %d | explained by discount %d | needs checking %d | no quotation linked %d"
                                             % (o["out"], len(same), len(explained), len(needs), len(unlinked))))
