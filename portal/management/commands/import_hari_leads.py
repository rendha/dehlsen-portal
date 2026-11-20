"""Add Hari's lead sheet (MARKETING and Residential visit tabs) to the Leads, entered by and given to Hari.
Closed / work-complete rows are left out (they are customers already).  Already-present leads (same phone, or same name for Hari) are skipped.
Run:  python manage.py import_hari_leads --file HARI_1.xlsx --dry-run     then again without --dry-run."""
import re

import openpyxl
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from portal.models import Lead, LeadEvent

STATUS = ("postpone", "complete", "quotation", "bill", "shared", "closed", "yet to", "discussion", "documentation", "interested", "follow", "requir", "pending")
PLACES = {"ekm": "Ernakulam", "plkd": "Palakkad"}


def digits(v):
    return re.sub(r"\D", "", str(int(v)) if isinstance(v, float) else str(v))


def parse(row):
    cells = [c for c in row if c is not None and str(c).strip()]
    if len(cells) < 2:
        return None
    name = str(cells[0]).strip()
    if name.lower() == "transformer":
        return None                                      # a column-heading row inside the sheet
    phone = kw = status = refer = ""
    place = []
    for c in cells[1:]:
        t = str(c).strip()
        low = t.lower()
        if len(digits(c)) >= 10 and not phone and not re.search(r"[a-z]", low):
            phone = digits(c)[-10:]
        elif re.fullmatch(r"\d+\s*kw", low.replace(" ", "")) or re.fullmatch(r"\d+\s*kw", low):
            kw = re.sub(r"\D", "", t) + " kW"
        elif "ref" in low or low.endswith(" lead"):
            refer = t
        elif any(s in low for s in STATUS):
            status = (status + ", " + t) if status else t
        elif len(digits(c)) >= 10 and not re.search(r"[a-z]", low):
            continue                                    # the phone number typed twice
        else:
            place.append(PLACES.get(low, t.title()))
    if not (phone or status or place or kw):
        return None
    return {"name": name.title(), "phone": phone, "kw": kw, "status": status, "refer": refer, "area": ", ".join(place)}


def priority(status):
    s = status.lower()
    if any(k in s for k in ("quotation", "documentation", "bill")):
        return Lead.HOT
    if any(k in s for k in ("shared", "discussion", "follow", "interested", "pending", "yet to")):
        return Lead.MEDIUM
    return Lead.COLD


class Command(BaseCommand):
    help = "Import Hari's MARKETING and Residential visit leads."

    def add_arguments(self, p):
        p.add_argument("--file", required=True)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--user", default="hari", help="part of Hari's username / first name")

    def handle(self, *a, **o):
        U = get_user_model()
        from django.db.models import Q
        users = list(U.objects.filter(Q(username__icontains=o["user"]) | Q(first_name__icontains=o["user"]), is_active=True))
        if len(users) != 1:
            raise CommandError("Found %d users for '%s': %s - use --user with a clearer part of his username." % (len(users), o["user"], [u.username for u in users]))
        hari = users[0]
        wb = openpyxl.load_workbook(o["file"], data_only=True)
        todo, skipped = [], []
        for tab, start, resid in (("MARKETING", 6, False), ("Residential visit", 5, True)):
            for r in wb[tab].iter_rows(min_row=start, values_only=True):
                d = parse(r)
                if not d:
                    continue
                low = d["status"].lower()
                if "closed" in low or "complete" in low:
                    skipped.append((tab, d["name"], d["status"]))
                    continue
                d["tab"], d["resid"] = tab, resid
                todo.append(d)
        have = set(Lead.objects.exclude(phone="").values_list("phone", flat=True))
        names = {n.lower() for n in Lead.objects.filter(entered_by=hari).values_list("customer_name", flat=True)}
        new, dup = [], []
        for d in todo:
            if (d["phone"] and d["phone"][-10:] in {p[-10:] for p in have}) or d["name"].lower() in names:
                dup.append(d)
            else:
                new.append(d)
        for d in new:
            self.stdout.write("ADD  %-22s %-11s %-6s %-26s %-24s %s" % (d["name"][:22], d["phone"], d["kw"], d["area"][:26], d["status"][:24], d["refer"]))
        for d in dup:
            self.stdout.write("HAVE %s" % d["name"])
        for s in skipped:
            self.stdout.write("LEFT OUT (customer already) %s - %s" % (s[1], s[2]))
        self.stdout.write("%d to add, %d already there, %d left out. Leads will be entered by and given to %s." % (len(new), len(dup), len(skipped), hari.get_username()))
        if o["dry_run"]:
            self.stdout.write("DRY RUN - nothing saved.")
            return
        with transaction.atomic():
            for d in new:
                note = "From Hari's lead sheet (%s)." % d["tab"]
                for k, lab in (("kw", "Size"), ("status", "Status"), ("refer", "Referral")):
                    if d[k]:
                        note += " %s: %s." % (lab, d[k])
                lost = "requir" in d["status"].lower() and "no" in d["status"].lower()
                lead = Lead.objects.create(customer_name=d["name"], phone=d["phone"], area=d["area"], need=Lead.CALL, priority=priority(d["status"]), note=note,
                                           entered_by=hari, assigned_to=hari, next_step="Follow up", customer_type="residential" if d["resid"] else "",
                                           lost=lost, lost_reason="No requirement" if lost else "")
                LeadEvent.objects.create(lead=lead, by=hari, kind="entered", text="Added from Hari's lead sheet")
        self.stdout.write("Saved.")
