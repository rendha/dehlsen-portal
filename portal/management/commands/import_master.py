"""py manage.py import_master [--dry-run] [--overwrite]  -  loads the Project Master workbook (portal/data/master_seed.json) into the projects.

Matches each workbook customer to a project exactly like import_kseb (project id, payment row, name, phone, close spelling); a customer who is
not found is CREATED.  By default only EMPTY values are filled and every difference in the core data (kW, panel, inverter, scheme, sales person...)
is listed.  With --overwrite the core data of the workbook replaces what the portal has (the workbook is then the master).  Contractor amounts,
invoice, handover and warranty are filled when empty (or replaced with --overwrite)."""
import datetime
import json
from difflib import SequenceMatcher
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import Command as Kseb, compact, last10, same_person, stage_ticks, _date
from portal.models import Collection, ProjectWork

TEXT = ["email", "alt_phone", "pincode", "district", "region", "segment", "load_change", "almm", "inverter_phase", "inverter_model", "roof_type",
        "energy_meter_make", "net_meter_make", "kseb_ref", "docs_status", "reg_receipt", "inspection_status", "subsidy_status", "bank_details",
        "programming_notes", "kseb_notes", "handover_status", "handover_mode", "handed_over_by", "arn", "inverter_serial", "energy_meter_serial",
        "net_meter_serial", "panel_serials", "invoice_no", "electrical_contractor", "structure_contractor"]
CORE = ["phone", "site_address", "map_link", "kw", "panel_make", "inverter_make", "scheme", "sales_person", "engineer", "system"]
NUM = ["panel_wp", "dc_kwp", "ac_kw", "quote_value", "invoice_value", "electrical_amount", "electrical_paid", "structure_amount", "structure_paid"]
INT = ["panel_count", "panel_warranty_yrs", "panel_perf_yrs", "inverter_warranty_yrs", "workmanship_yrs"]
DATES = ["invoice_date", "handover_date", "warranty_start"]


def yes(v):
    return {"yes": True, "y": True, "no": False, "n": False}.get(str(v).strip().lower())


class Command(BaseCommand):
    help = "Load the Project Master workbook into the projects (fills empty values; --overwrite lets the workbook win)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--overwrite", action="store_true", help="the workbook's core data replaces the portal's")

    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "data" / "master_seed.json").read_text(encoding="utf-8"))
        dry, over = options["dry_run"], options["overwrite"]
        finder = Kseb()
        works = list(ProjectWork.objects.select_related("collection"))
        collections = {c.project_id: c for c in Collection.objects.all()}
        by_id = {w.project_id: w for w in works if w.project_id}
        by_cname = {}
        for w in works:
            by_cname.setdefault(compact(w.name), w)
        by_phone = {last10(w.phone): w for w in works if last10(w.phone)}
        hit = made = diffs = 0
        claimed = set()
        conflicts = 0
        for pid, r in sorted(data.items()):
            name = r.get("name") or ""
            if not name:
                continue
            w, why = finder.find(pid, r, works, by_id, by_cname, by_phone, collections, [])
            # matched WITHOUT the project id: refuse when the names are unlike (same phone only) or when both have a phone and the phones differ (two people with one name)
            if w is not None and w.project_id != pid and not str(why).startswith("payment sheet"):
                p1, p2 = last10(r.get("phone", "")), last10(w.phone)
                ka, kb = compact(name), compact(w.name)
                alike = same_person(name, w.name) or (ka and kb and (ka in kb or kb in ka or SequenceMatcher(None, ka, kb).ratio() >= 0.75))
                if (why == "same phone" and not alike) or (p1 and p2 and p1 != p2):
                    self.stdout.write("   skip  %s  %s  !=  %s %s  (%s) - not the same customer" % (pid, name, w.project_id or "no id", w.name, why or "same name"))
                    w = None
            # a guessed (name / phone) match is refused when that portal project already has a DIFFERENT project id or was already taken by another row
            if w is not None and why and ((w.project_id and w.project_id != pid) or id(w) in claimed):
                self.stdout.write("   skip  %s  %s  !=  %s %s  (%s) - treated as a different project" % (pid, name, w.project_id, w.name, why))
                w = None
            # same project id but clearly another customer (different name AND different phone): do not touch it, list it for a manual check
            if w is not None and w.project_id == pid and w.pk:
                a, b = compact(name), compact(w.name)
                p1, p2 = last10(r.get("phone", "")), last10(w.phone)
                if a and b and not same_person(name, w.name) and SequenceMatcher(None, a, b).ratio() < 0.6 and p1 and p2 and p1 != p2:
                    conflicts += 1
                    self.stdout.write("   CONFLICT %s  workbook '%s' %s  /  portal '%s' %s  - left untouched" % (pid, name, p1, w.name, p2))
                    continue
            if w is not None:
                claimed.add(id(w))
            if w is None:
                w = ProjectWork(name=name[:200], name_key=compact(name), project_id=pid)
                if pid in collections:
                    w.collection = collections[pid]
                works.append(w)
                claimed.add(id(w))
                made += 1
                self.stdout.write("   NEW   %s  %s" % (pid, name))
            else:
                hit += 1
                if why:
                    self.stdout.write("   match %s  %s  ->  %s  (%s)" % (pid, name, w.name, why))
            if not w.project_id:
                w.project_id = pid
            # core data: fill empties, list (or overwrite) differences
            for f in CORE:
                new = (r.get(f) or "").strip() if isinstance(r.get(f), str) else r.get(f)
                if not new:
                    continue
                old = getattr(w, f)
                if not old:
                    setattr(w, f, new)
                elif str(old).strip().lower() != str(new).strip().lower():
                    diffs += 1
                    if over:
                        setattr(w, f, new)
                    else:
                        self.stdout.write("   differs %s %s: portal '%s' / workbook '%s'" % (pid, f, str(old)[:40], str(new)[:40]))
            if r.get("consumer_no") and not w.kseb_consumer_no:
                w.kseb_consumer_no = r["consumer_no"]
            if r.get("booking_date") and (not w.booking_date or over):
                w.booking_date = _date(r["booking_date"])
            for f in TEXT:
                if r.get(f) and (not getattr(w, f) or over):
                    setattr(w, f, r[f])
            for f in NUM:
                if r.get(f) is not None and (not getattr(w, f) or over):
                    setattr(w, f, Decimal(str(r[f])))
            for f in INT:
                if r.get(f) is not None and (not getattr(w, f) or over):
                    setattr(w, f, int(r[f]))
            for f in DATES:
                if r.get(f) and (not getattr(w, f) or over):
                    setattr(w, f, _date(r[f]))
            if r.get("panel_at_site") and w.panel_at_site is None:
                w.panel_at_site = yes(r["panel_at_site"])
            if r.get("inverter_at_site") and w.inverter_at_site is None:
                w.inverter_at_site = yes(r["inverter_at_site"])
            if r.get("docs_given") and (not w.docs_given or over):
                w.docs_given = r["docs_given"]
            if r.get("stage") and (over or w.done_count == 0 or not w.project_stage):      # never overwrite the stage of a project the team has already ticked
                w.project_stage = r["stage"]
                if w.done_count == 0:
                    for f in stage_ticks(r["stage"]):
                        setattr(w, f, True)
            kseb = dict(w.kseb or {})
            for k, v in (r.get("kseb") or {}).items():
                if k == "feasibility":
                    if not w.feasibility_date or over:
                        w.feasibility_date = _date(v)
                elif k == "commissioning":
                    if not w.commission_date or over:
                        w.commission_date = _date(v)
                elif k not in kseb or over:
                    kseb[k] = v
            w.kseb = kseb
            if kseb.get("reg_paid"):
                w.registration_paid = True
            if w.handover_date or (w.handover_status or "").lower() == "handed over":
                w.handover = True
            if r.get("remarks") and not w.remarks:
                w.remarks = r["remarks"][:300]
            if not dry:
                w.save()
            by_id[pid] = w
            by_cname.setdefault(compact(w.name), w)
            if last10(w.phone):
                by_phone.setdefault(last10(w.phone), w)
        if dry:
            self.stdout.write("DRY RUN: nothing was saved.")
        self.stdout.write("%d id conflicts left untouched (see CONFLICT lines)" % conflicts)
        self.stdout.write(self.style.SUCCESS("matched %d projects, created %d new, %d core differences %s" % (
            hit, made, diffs, "(replaced)" if over else "(kept - use --overwrite to take the workbook's)")))
