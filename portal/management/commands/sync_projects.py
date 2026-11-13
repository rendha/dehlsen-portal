"""py manage.py sync_projects [--apply]  -  make a project for every confirmed customer (quotation) that has none, and link the ones already there.
Without --apply it only prints what it WOULD do.  It runs by itself every day and whenever a quotation is confirmed."""
from django.core.management.base import BaseCommand

from portal.project_sync import ensure_projects


class Command(BaseCommand):
    help = "Create / link projects for the confirmed customers."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        created, linked = ensure_projects(dry=not options["apply"], say=self.stdout.write)
        self.stdout.write(self.style.SUCCESS("%s: %d new, %d linked to a project already there." % ("done" if options["apply"] else "dry run (nothing saved)", created, linked)))
