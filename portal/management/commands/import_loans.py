"""py manage.py import_loans [--dry-run]  -  marks the bank-loan customers of the MNRE loan sheet as 'Bank loan' on their projects.
Source: portal/data/loans_seed.json (the loan sheet without the cancelled / ready-cash rows and without the customers whose sales person is Nadheem).
For each customer found in the portal (by phone + name, else a very close name): payment mode = Bank loan, loan amount, the bank's first / second payment dates and
amount of the first payment (only where the portal has none yet), and the bank name is added to the remarks.  Customers that are not in the portal are only listed.
Never overwrites a value that is already filled."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.models import ProjectWork


def key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def tail(s):
    return re.sub(r"\D", "", s or "")[-10:]


class Command(BaseCommand):
    help = "Mark the bank-loan customers (loan sheet) as Bank loan on their projects."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        rows = json.loads((Path(__file__).resolve().parents[2] / "data" / "loans_seed.json").read_text(encoding="utf-8"))
        works = list(ProjectWork.objects.all())
        done = missing = ambiguous = 0
        for o in rows:
            n = key(o["name"])
            cands = [w for w in works if o["phone"] and o["phone"] in (tail(w.phone), tail(getattr(w, "alt_phone", "")))
                     and (SequenceMatcher(None, n, key(w.name)).ratio() >= 0.55 or n[:4] in key(w.name) or key(w.name)[:4] in n)]
            if not cands:
                close = sorted(((SequenceMatcher(None, n, key(w.name)).ratio(), w) for w in works), key=lambda t: -t[0])
                cands = [w for s, w in close[:2] if s >= 0.85][:1]
            if not cands:
                missing += 1
                self.stdout.write("   NOT IN PORTAL  %-30s %s  %s  loan %s  (%s)" % (o["name"][:30], o["phone"], o["bank"], o["loan_amount"], o["status"] or "no status"))
                continue
            if len(cands) > 1:                                   # several projects of this customer: the newest booking
                cands.sort(key=lambda w: (w.booking_date is not None, w.booking_date, w.project_id or ""), reverse=True)
                ambiguous += 1
            w = cands[0]
            changes = []
            if not w.is_loan:
                w.payment_mode = ProjectWork.LOAN
                changes.append("bank loan")
            if o["loan_amount"] and not w.loan_amount:
                w.loan_amount = o["loan_amount"]
                changes.append("loan %s" % o["loan_amount"])
            if o["b1_date"] and not w.bank1_received_on:
                w.bank1_received_on = o["b1_date"]
                changes.append("1st payment %s" % o["b1_date"])
                if o["b1_amount"]:
                    w.bank1_amount = o["b1_amount"]
            if o["b2_date"] and not w.bank2_received_on:
                w.bank2_received_on = o["b2_date"]
                changes.append("2nd payment %s" % o["b2_date"])
            note = "Loan: %s %s" % (o["bank"], o["branch"])
            if o["bank"] and "loan:" not in (w.remarks or "").lower():
                w.remarks = (((w.remarks + "\n") if w.remarks else "") + note.strip())[:300]
                changes.append("remarks")
            self.stdout.write("   %-12s %-28s %s" % (w.project_id or "no id", w.name[:28], ", ".join(changes) or "already set"))
            if changes:
                done += 1
                if not dry:
                    w.save()
        self.stdout.write(self.style.SUCCESS("%s: %d projects marked as bank loan, %d not in the portal, %d customers had several projects (the newest was used)." % ("DRY RUN, nothing saved" if dry else "Done", done, missing, ambiguous)))
