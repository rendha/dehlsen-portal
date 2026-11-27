"""Put a folder of installation photos into the Sales gallery.

    python manage.py load_gallery_photos gallery_samples --dry-run     (shows what it would add, changes nothing)
    python manage.py load_gallery_photos gallery_samples               (adds them)

Each file is named   Title__Capacity__Place__kind.jpg   (two underscores between the parts), for example
    PVS Prestige Apartment__60 kW__Palazhi, Kozhikode__flat.jpg
Capacity and place may be empty (keep the underscores).  kind is one of: home, flat, commercial, industrial, other.
Several photos of one project: add a number at the end (PVS Prestige Apartment__60 kW__Palazhi, Kozhikode__flat__2.jpg).
Photos with the same title and place go into the same project; the one with no number (or the lowest) is the cover.
A file that was already loaded is skipped, so it is safe to run again.
"""
import os

from django.core.management.base import BaseCommand, CommandError

from portal.gallery import FULL_SIDE, THUMB_SIDE, _shrink
from portal.models import GalleryPhoto, GalleryProject

KINDS = dict(GalleryProject.KINDS)


class Command(BaseCommand):
    help = "Load a folder of photos into the gallery."

    def add_arguments(self, p):
        p.add_argument("folder")
        p.add_argument("--dry-run", action="store_true")

    def handle(self, *a, **o):
        folder = o["folder"]
        if not os.path.isdir(folder):
            raise CommandError("Folder not found: %s" % folder)
        made = skipped = 0
        files = []
        for name in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(name)
            if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            parts = stem.split("__")
            if len(parts) not in (4, 5) or parts[3].strip().lower() not in KINDS:
                self.stdout.write("skip  %s  (name must be Title__Capacity__Place__kind  or  ...__kind__2)" % name)
                skipped += 1
                continue
            order = int(parts[4]) if len(parts) == 5 and parts[4].strip().isdigit() else 1
            title, capacity, place, kind = [x.strip() for x in parts[:4]]
            files.append((title, place, order, name, capacity, kind.lower()))
        for title, place, order, name, capacity, kind in sorted(files):
            if GalleryPhoto.objects.filter(source=name).exists():
                self.stdout.write("skip  %-40s already in the gallery" % name)
                skipped += 1
                continue
            old = GalleryPhoto.objects.filter(project__title=title, project__place=place, source="").order_by("id").first()
            if old is not None and order == 1:                 # loaded by the first version of this command: just remember its file name
                if not o["dry_run"]:
                    GalleryPhoto.objects.filter(pk=old.pk).update(source=name)
                self.stdout.write("skip  %-40s already in the gallery" % name)
                skipped += 1
                continue
            self.stdout.write("%s %-28s %-8s %-22s %-10s #%d" % ("would add" if o["dry_run"] else "add", title, capacity, place, kind, order))
            made += 1
            if o["dry_run"]:
                continue
            with open(os.path.join(folder, name), "rb") as fh:
                raw = fh.read()
            project = GalleryProject.objects.filter(title=title, place=place).first() or GalleryProject.objects.create(
                title=title, capacity=capacity, place=place, kind=kind)
            ph = GalleryPhoto.objects.create(project=project, data=_shrink(raw, FULL_SIDE, 82), thumb=_shrink(raw, THUMB_SIDE, 75), source=name)
            if project.cover_id is None:
                project.cover = ph
                project.save(update_fields=["cover"])
        self.stdout.write("%s %d, skipped %d.%s" % ("Would add" if o["dry_run"] else "Added", made, skipped,
                                                    "  Dry run - nothing changed." if o["dry_run"] else ""))
