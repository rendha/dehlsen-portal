"""py manage.py import_kseb  -  loads the KSEB step dates, serial numbers, contractor payouts and warranty of the Project List workbook
(portal/data/kseb_seed.json) into the projects.  Fills only EMPTY values, so it is safe to run again.

How a workbook customer is matched to a project already in the portal (first hit wins):
  1. the same Project ID (DH26-27/xxx)   2. the payment sheet row with that Project ID, and the project linked to it
  3. the same name   4. the same phone number (last 10 digits)   5. a very close spelling (also compared without spaces: SNO FIELD = Snowfield)
  6. a close spelling in the same place.
Nobody matched is CREATED as a new project (a row without a name is skipped).  Every match that is not an exact name is printed, so you can check it."""
import datetime
import json
import re
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.models import Collection, ProjectWork


def _date(s):
    try:
        return datetime.date.fromisoformat(s) if s else None
    except ValueError:
        return None


def compact(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", (s or "").lower()))        # the bracket "(PRADEEP)" is not part of the name


def tokens(s):
    return set(re.sub(r"\(.*?\)", " ", (s or "").lower()).replace(".", " ").split())


def same_person(a, b):
    """The shorter name is contained in the longer one (ADARSH / ADARSH N V, GIRISH / GIRISH R): the extra words are only initials."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return small <= big and sum(len(t) for t in small) >= 6 and all(len(t) <= 2 for t in big - small)


def last10(s):
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


# what each "Project Stage" of the workbook means for the stage ticks (each stage includes the ones before it)
_STAGE_ORDER = ["Feasibility Approved", "Material Dispatched", "Installation In Progress", "Structure Work", "Panel Fixing", "Electrical Work",
                "Inverter / Final Connection", "Installation Complete", "Net Meter / Inspection", "Commissioned"]
_STAGE_TICKS = {
    "Feasibility Approved": ["site_estimation", "design"],
    "Material Dispatched": ["bos", "inverter_done", "panel_done"],
    "Structure Work": ["structure"],
    "Electrical Work": ["electrical"],
    "Installation Complete": ["inv_program"],
    "Net Meter / Inspection": ["testing"],
    "Commissioned": ["meter_fix"],
}


def stage_ticks(stage):
    if stage not in _STAGE_ORDER:
        return []
    out = []
    for st in _STAGE_ORDER[: _STAGE_ORDER.index(stage) + 1]:
        out += _STAGE_TICKS.get(st, [])
    return out


class Command(BaseCommand):
    help = "Load KSEB dates, serials, contractors and warranty into the projects; create the customers that are missing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only print the matches and the new customers; save nothing.")

    def find(self, pid, r, works, by_id, by_cname, by_phone, collections_by_id, notes):
        w = by_id.get(pid)
        if w:
            return w, ""
        col = collections_by_id.get(pid)
        if col:
            for x in works:
                if x.collection_id == col.pk:
                    return x, "payment sheet %s" % pid
        name = r.get("name", "")
        key = compact(name)
        if key and key in by_cname:
            return by_cname[key], ""
        ph = last10(r.get("phone", ""))
        if ph and ph in by_phone:
            return by_phone[ph], "same phone"
        names = [col.customer] if col else []
        best, hit = 0.0, None
        for x in works:
            for cand in [x.name] + ([x.collection.customer] if x.collection_id else []):
                s = 0.9 if same_person(name, cand) else SequenceMatcher(None, key, compact(cand)).ratio()
                loc = compact(r.get("location", ""))
                same_place = bool(loc) and loc in compact("%s %s %s" % (x.location, x.site_address, x.collection.region if x.collection_id else ""))
                if s >= 0.88 or (s >= 0.82 and same_place):
                    if s > best:
                        best, hit = s, x
        if hit:
            return hit, "close spelling (%.0f%%)" % (best * 100)
        return None, ""

    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "data" / "kseb_seed.json").read_text(encoding="utf-8"))
        works = list(ProjectWork.objects.select_related("collection"))
        collections = {c.project_id: c for c in Collection.objects.all()}
        by_id = {w.project_id: w for w in works if w.project_id}
        by_cname = {}
        for w in works:
            by_cname.setdefault(compact(w.name), w)
        by_phone = {last10(w.phone): w for w in works if last10(w.phone)}
        dry = options["dry_run"]
        hit = made = skipped = 0
        for pid, r in data.items():
            name = r.get("name") or (collections[pid].customer if pid in collections else "")
            if not name:
                skipped += 1
                self.stdout.write("   skipped %s (no name)" % pid)
                continue
            r = dict(r, name=name)
            w, why = self.find(pid, r, works, by_id, by_cname, by_phone, collections, [])
            col_note = ""
            if w is None and pid not in collections:
                best, bc = 0.0, None
                for c in collections.values():
                    s2 = 0.95 if same_person(name, c.customer) else SequenceMatcher(None, compact(name), compact(c.customer)).ratio()
                    if last10(r.get("phone", "")) and last10(r.get("phone", "")) == last10(c.phone):
                        s2 = 1.0
                    if s2 > best:
                        best, bc = s2, c
                if bc is not None and best >= 0.85:
                    for x in works:
                        if x.collection_id == bc.pk:
                            w, col_note = x, "payment row %s %s" % (bc.project_id, bc.customer)
                            break
                    else:
                        collections = dict(collections)
                        collections[pid] = bc                  # create the new project and link it to this payment row
                        col_note = "payment row %s %s" % (bc.project_id, bc.customer)
                    self.stdout.write("   payment match %s  %s  ->  %s  (%d%%)" % (pid, name, col_note, best * 100))
            if w is None and not dry and ProjectWork.objects.filter(project_id=pid).exists():
                w = ProjectWork.objects.get(project_id=pid)
            if w is None:
                if pid in collections:
                    name = collections[pid].customer or name        # use the spelling of the payment sheet, so the store and payments find it
                w = ProjectWork(name=name[:200], name_key=compact(name), project_id=pid)
                works.append(w)
                made += 1
                self.stdout.write("   NEW   %s  %s%s" % (pid, name, "  (linked to its payment row)" if pid in collections else "  (no payment row found)"))
            else:
                hit += 1
                if why:
                    self.stdout.write("   match %s  %s  ->  %s  (%s)" % (pid, name, w.name, why))
            if not w.project_id:
                w.project_id = pid
            if not w.collection_id and pid in collections:
                w.collection = collections[pid]
            for f in ("phone", "site_address", "location", "map_link", "kw", "panel_make", "inverter_make", "sales_person", "engineer"):
                if r.get(f) and not getattr(w, f):
                    setattr(w, f, r[f][:150] if f == "location" else r[f])
            if r.get("booking_date") and not w.booking_date:
                w.booking_date = _date(r["booking_date"])
            kseb = dict(w.kseb or {})
            for k, v in (r.get("kseb") or {}).items():
                if k == "feasibility":
                    w.feasibility_date = w.feasibility_date or _date(v)
                elif k == "commissioning":
                    w.commission_date = w.commission_date or _date(v)
                else:
                    kseb.setdefault(k, v)
            w.kseb = kseb
            if kseb.get("reg_paid"):
                w.registration_paid = True
            if r.get("consumer_no") and not w.kseb_consumer_no:
                w.kseb_consumer_no = r["consumer_no"]
            for f in ("arn", "scheme", "panel_serials", "inverter_serial", "energy_meter_serial", "net_meter_serial",
                      "electrical_contractor", "structure_contractor", "invoice_no"):
                if r.get(f) and not getattr(w, f):
                    setattr(w, f, r[f])
            for f in ("electrical_amount", "electrical_paid", "structure_amount", "structure_paid"):
                if r.get(f) and not getattr(w, f):
                    setattr(w, f, Decimal(str(r[f])))
            for f in ("panel_count", "panel_warranty_yrs", "inverter_warranty_yrs", "workmanship_yrs"):
                if r.get(f) and not getattr(w, f):
                    setattr(w, f, r[f])
            for f in ("invoice_date", "handover_date"):
                if r.get(f) and not getattr(w, f):
                    setattr(w, f, _date(r[f]))
            if r.get("stage") and w.done_count == 0:                 # nobody has ticked this customer yet: take the ticks from the workbook's Project Stage
                for f in stage_ticks(r["stage"]):
                    setattr(w, f, True)
                if r["stage"] == "Commissioned" and not w.work_status:
                    w.work_status = "Commissioned (from the Project List)"
            if w.handover_date:
                w.handover = True
            if not dry:
                w.save()
            by_id[pid] = w
            by_cname.setdefault(compact(w.name), w)          # so a second row of the same customer finds this one and is not created again
            if last10(w.phone):
                by_phone.setdefault(last10(w.phone), w)
        if dry:
            self.stdout.write("DRY RUN: nothing was saved.")
        self.stdout.write(self.style.SUCCESS("updated %d projects, created %d new, skipped %d without a name" % (hit, made, skipped)))
