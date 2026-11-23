"""py manage.py check_mixed  -  READ-ONLY.  Lists projects whose data looks mixed up.  Nothing is changed.

  A. ID    the project with this id has another customer's name in the Project Master workbook (name and phone/address differ)
  B. LINK  the payment row linked to the project belongs to another customer (different name)
Ask for it with  > /tmp/mixed.txt  or  | grep -E "^(ID|LINK)" """
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import compact, last10, same_person
from portal.models import ProjectWork


def alike(a, b):
    ka, kb = compact(a), compact(b)
    if not ka or not kb:
        return True                       # nothing to compare
    return same_person(a, b) or ka in kb or kb in ka or SequenceMatcher(None, ka, kb).ratio() >= 0.75


class Command(BaseCommand):
    help = "Read-only: list projects that look mixed up (name from one customer, details from another)."

    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "data" / "master_seed.json").read_text(encoding="utf-8"))
        works = list(ProjectWork.objects.select_related("collection"))
        by_id = {w.project_id: w for w in works if w.project_id}
        n_id = n_link = 0
        for pid, r in sorted(data.items()):
            w = by_id.get(pid)
            if not w:
                continue
            same_name = alike(r.get("name", ""), w.name)
            p1, p2 = last10(r.get("phone", "")), last10(w.phone)
            addr_w = compact((w.site_address or "")[:25])
            addr_r = compact((r.get("site_address") or "")[:25])
            if not same_name:
                n_id += 1
                why = "phone differs" if (p1 and p2 and p1 != p2) else "phone same" if (p1 and p1 == p2) else "phone unknown"
                self.stdout.write("ID    %-13s portal '%s' %s | workbook '%s' %s | %s" % (pid, w.name, w.phone or "-", r.get("name"), r.get("phone") or "-", why))
            elif addr_w and addr_r and addr_w != addr_r and p1 and p2 and p1 != p2:
                n_id += 1
                self.stdout.write("ID    %-13s same name '%s' but phone AND address differ: portal %s / workbook %s" % (pid, w.name, w.phone, r.get("phone")))
        for w in works:
            c = w.collection
            if c and not alike(c.customer, w.name):
                n_link += 1
                self.stdout.write("LINK  %-13s project '%s' %s | payment row %s '%s' booked %s" % (w.project_id or "no id", w.name, w.phone or "-", c.project_id, c.customer, c.booking_date))
        self.stdout.write(self.style.SUCCESS("%d id mismatches, %d wrong payment links (nothing was changed)." % (n_id, n_link)))
