"""py manage.py relink_payments [--dry-run]  -  links every project to the payment row of the SAME customer.

The payment sheet numbers some customers differently from the Project Master (RAYEESUDHEEN is 157 there, 160 in the master; PRAMOD KUMAR 160 there, 152 in the master),
so a project was linked to another customer's payment row: it showed that name, deal value, received and balance.
  1. a project whose payment row belongs to another name is moved to the payment row with its own name (or unlinked when there is none);
  2. a payment row that has no project is linked to the project with its name.
Only the link changes.  Payment amounts and the payment sheet's own numbers are never edited."""
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import compact, same_person
from portal.models import Collection, ProjectWork


def score(a, b):
    ka, kb = compact(a), compact(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if same_person(a, b):
        return 0.95
    return SequenceMatcher(None, ka, kb).ratio()


class Command(BaseCommand):
    help = "Link each project to the payment row of the same customer."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        works = list(ProjectWork.objects.select_related("collection"))
        cols = list(Collection.objects.all())
        moved = unlinked = linked = 0

        def money(c):
            return "deal %s received %s" % (c.net_value, c.received) if c else "-"

        # 1. projects linked to another customer's payment row
        for w in works:
            c = w.collection
            if not c or score(c.customer, w.name) >= 0.85:
                continue
            best, hit = 0.0, None
            for x in cols:
                s = score(x.customer, w.name)
                if s > best:
                    best, hit = s, x
            if hit and best >= 0.88 and hit.pk != c.pk:
                self.stdout.write("   MOVE   %-12s %-26s  payment row '%s' (%s)  ->  '%s' %s (%s)" % (w.project_id or "no id", w.name[:26], c.customer, c.project_id, hit.customer, hit.project_id, money(hit)))
                moved += 1
                w.collection = hit
            else:
                self.stdout.write("   UNLINK %-12s %-26s  payment row '%s' (%s, %s) is another customer; no payment row of this name" % (w.project_id or "no id", w.name[:26], c.customer, c.project_id, money(c)))
                unlinked += 1
                w.collection = None
            if not dry:
                w.save(update_fields=["collection"])
        # 2. payment rows left without a project
        taken = {w.collection_id for w in works if w.collection_id}
        for c in cols:
            if c.pk in taken:
                continue
            best, hit = 0.0, None
            for w in works:
                if w.collection_id:
                    continue
                s = score(c.customer, w.name)
                if s > best:
                    best, hit = s, w
            if hit and best >= 0.88:
                self.stdout.write("   LINK   %-12s %-26s  <- payment row '%s' (%s, %s)" % (hit.project_id or "no id", hit.name[:26], c.customer, c.project_id, money(c)))
                linked += 1
                hit.collection = c
                taken.add(c.pk)
                if not dry:
                    hit.save(update_fields=["collection"])
        self.stdout.write(self.style.SUCCESS("%s: %d projects moved to their own payment row, %d unlinked, %d payment rows newly linked." % ("DRY RUN, nothing saved" if dry else "Done", moved, unlinked, linked)))
