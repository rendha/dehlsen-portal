"""py manage.py repair_mixed [--dry-run]  -  one-time repair of the customers that the Project Master import mixed up (found with check_mixed).

  1. DH26-27/160  the project that holds Rayeesudheen's phone, address, e-mail and consumer no. gets his name RAYEESUDHEEN CV (it was a test name).
  2. DH26-27/155  JAYARAJAN T P: the e-mail / pincode of another customer are replaced by the workbook's.
  3. DH26-27/153  FEBINA P P: the pincode is the workbook's.
  4. HAJARA P P (DH25-26/011), AL FALAH MADRASA (DH25-26/029), LIC VAIKOM (DH24-25/017), BASHEER (DH24-25/053) are different customers from the ones the workbook
     numbers so: the project id is taken off, and every value that is exactly the workbook's other customer's (filled in by the import) is cleared.
     The workbook's customers are then added as their own projects by  import_master.
Always run with --dry-run first."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import compact
from portal.models import ProjectWork

DETACH = [("DH25-26/011", "hajarapp"), ("DH25-26/029", "alfalahmadrasa"), ("DH24-25/017", "licvaikom"), ("DH24-25/053", "basheer")]
FIELDS = ["email", "alt_phone", "pincode", "district", "region", "segment", "load_change", "almm", "inverter_phase", "inverter_model", "roof_type", "energy_meter_make",
          "net_meter_make", "kseb_ref", "docs_status", "reg_receipt", "inspection_status", "subsidy_status", "bank_details", "programming_notes", "kseb_notes",
          "handover_status", "handover_mode", "handed_over_by", "arn", "inverter_serial", "energy_meter_serial", "net_meter_serial", "panel_serials", "invoice_no",
          "electrical_contractor", "structure_contractor", "site_address", "map_link", "kw", "panel_make", "inverter_make", "scheme", "sales_person", "engineer", "system",
          "panel_wp", "dc_kwp", "ac_kw", "quote_value", "invoice_value", "electrical_amount", "electrical_paid", "structure_amount", "structure_paid",
          "panel_count", "panel_warranty_yrs", "panel_perf_yrs", "inverter_warranty_yrs", "workmanship_yrs", "remarks"]


class Command(BaseCommand):
    help = "Repair the customers mixed up by the master import (run check_mixed first)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        data = json.loads((Path(__file__).resolve().parents[2] / "data" / "master_seed.json").read_text(encoding="utf-8"))

        def save(w, note):
            self.stdout.write("   " + note)
            if not dry:
                w.save()

        # 1. Rayeesudheen
        r = data["DH26-27/160"]
        for w in ProjectWork.objects.filter(project_id="DH26-27/160"):
            if compact(w.name) != compact(r["name"]):
                if "9633823344" in (w.phone or "") or "1167344012503" in (w.kseb_consumer_no or ""):
                    old = w.name
                    w.name, w.name_key = r["name"], compact(r["name"])
                    save(w, "DH26-27/160: '%s' -> '%s' (it holds his phone, address, e-mail and consumer no.)" % (old, r["name"]))
                else:
                    self.stdout.write("   DH26-27/160 '%s' has another phone - left alone, check it by hand" % w.name)
        # 2./3. e-mail and pincode of the wrong customer
        for pid, fields in (("DH26-27/155", ("email", "pincode")), ("DH26-27/153", ("pincode",))):
            r = data[pid]
            for w in ProjectWork.objects.filter(project_id=pid):
                for f in fields:
                    new = str(r.get(f) or "")
                    if str(getattr(w, f) or "") != new:
                        save(w, "%s %s: '%s' -> '%s'" % (pid, f, getattr(w, f), new or "(empty)"))
                        setattr(w, f, new)
        # 4. different customers that got the workbook's number
        for pid, key in DETACH:
            r = data[pid]
            for w in ProjectWork.objects.filter(project_id=pid):
                if compact(w.name) != key:
                    self.stdout.write("   %s is '%s', not '%s' - left alone" % (pid, w.name, key))
                    continue
                self.stdout.write("   %s '%s': the number is taken off (the workbook's customer there is '%s')" % (pid, w.name, r["name"]))
                for f in FIELDS:
                    v = r.get(f)
                    if v in (None, "") or getattr(w, f) in (None, ""):
                        continue
                    if str(getattr(w, f)).strip().lower() == str(v).strip().lower():
                        self.stdout.write("        clear %s = %s" % (f, str(v)[:40]))
                        setattr(w, f, "" if isinstance(getattr(w, f), str) else None)
                w.project_id = ""
                save(w, "saved '%s' without a project id" % w.name)
        self.stdout.write(self.style.SUCCESS("%s. Now run  import_master  to add the workbook's customers of those numbers." % ("DRY RUN, nothing saved" if dry else "Done")))
