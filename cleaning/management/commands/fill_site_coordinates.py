"""Fill in the missing map coordinates of customer sites, so "Locate our customer" can measure distance to them.

    python manage.py fill_site_coordinates                  LIST ONLY - shows what it would fill, changes nothing
    python manage.py fill_site_coordinates --links-only     list only sites that have a Google Maps link (exact pin)
    python manage.py fill_site_coordinates --save           saves what it found
    python manage.py fill_site_coordinates --save --links-only   saves only the exact (map link) ones

Order tried for every site that has no coordinates:
  1. its Google Maps link          -> exact pin, marked 'link'
  2. its location / address text   -> looked up on OpenStreetMap, only the AREA (village / town), marked 'place'
Places found outside Kerala are ignored.  Sites that already have coordinates are never touched.
"""
import time

from django.core.management.base import BaseCommand

from cleaning.geo import coords_from_text, geocode_place
from cleaning.models import Site

KERALA = (8.0, 13.6, 74.5, 77.6)   # lat min/max, lng min/max


def in_kerala(point):
    lat, lng = point
    return KERALA[0] <= lat <= KERALA[1] and KERALA[2] <= lng <= KERALA[3]


class Command(BaseCommand):
    help = "Fill missing site coordinates (list only unless --save)."

    def add_arguments(self, p):
        p.add_argument("--save", action="store_true", help="really save (default is list only)")
        p.add_argument("--links-only", action="store_true", help="use only Google Maps links, skip place-name lookups")

    def handle(self, *a, **o):
        save, links_only = o["save"], o["links_only"]
        sites = list(Site.objects.filter(latitude__isnull=True).select_related("customer").order_by("id"))
        found = {"link": 0, "place": 0}
        missed = []
        for site in sites:
            who = site.customer.name if site.customer_id else "(no customer)"
            point, src = None, ""
            if (site.google_map_link or "").strip():
                point = coords_from_text(site.google_map_link)
                if point and in_kerala(point):
                    src = "link"
                else:
                    point = None
            if point is None and not links_only:
                text = " ".join(x for x in ((site.location or "").strip(), (site.address or "").strip()) if x)
                if text:
                    time.sleep(1.1)                       # OpenStreetMap allows about one lookup a second
                    point = geocode_place(text)
                    if point and in_kerala(point):
                        src = "place"
                    else:
                        point = None
            if point is None:
                missed.append((site.id, who))
                continue
            found[src] += 1
            self.stdout.write("%-5s %-32s %-6s %.5f, %.5f" % (site.id, who[:32], src, point[0], point[1]))
            if save:
                site.latitude, site.longitude = point
                site.save(update_fields=["latitude", "longitude"])
        self.stdout.write("")
        self.stdout.write("Sites without coordinates: %d" % len(sites))
        self.stdout.write("  exact (from the map link): %d" % found["link"])
        self.stdout.write("  approximate (area looked up from the place name): %d" % found["place"])
        self.stdout.write("  still missing: %d" % len(missed))
        for sid, who in missed[:40]:
            self.stdout.write("    %-5s %s" % (sid, who))
        if len(missed) > 40:
            self.stdout.write("    ... and %d more" % (len(missed) - 40))
        self.stdout.write("SAVED." if save else "LIST ONLY - nothing changed. Add --save to save.")
