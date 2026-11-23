"""py manage.py fix_place [--dry-run]  -  the "Place" of many projects holds the customer's NAME (the old Daily Project Update import put the SITE column there).
Where the Place is the customer's name (same or a very close spelling) it is replaced by the project's district, else the payment region, else it is left empty.
A real place (Kozhikode, Kannur, Palazhi ...) is never touched."""
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand

from portal.management.commands.import_kseb import compact
from portal.models import ProjectWork


class Command(BaseCommand):
    help = "Replace a Place that is only the customer's name by the district / region."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        fixed = blank = 0
        for w in ProjectWork.objects.select_related("collection"):
            loc, name = compact(w.location), compact(w.name)
            if not loc or not name:
                continue
            if not (loc == name or loc in name or name in loc or SequenceMatcher(None, loc, name).ratio() >= 0.8):
                continue
            new = (w.district or (w.collection.region if w.collection_id else "") or "").strip()
            if dry and fixed + blank < 12:
                self.stdout.write("   %-12s %-30s place '%s' -> '%s'" % (w.project_id or "no id", w.name[:30], w.location, new or "(empty)"))
            if new:
                fixed += 1
            else:
                blank += 1
            if not dry:
                w.location = new[:150]
                w.save(update_fields=["location"])
        self.stdout.write(self.style.SUCCESS("%s: %d places set to the district/region, %d left empty (they only held the customer's name)." % ("DRY RUN" if dry else "Done", fixed, blank)))
