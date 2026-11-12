"""py manage.py setup_targets   -  creates the places, puts the people in them and enters the targets (safe to run again; it updates).

Financial year April - March:  Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar.  Change the numbers below and run it again any time.
A quarter with `fixed` is finished: its achieved amount is that number.  A quarter without it is counted from the confirmed customers.
Q3 of Kannur / Kozhikode is typed in for now (running total); when the real customers are in the app, empty "fixed achieved" in Admin to count live.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.models import Place, Profile, SalesTarget

L, CR = 100000, 10000000
D = datetime.date
Q = {"Q1": (D(2026, 4, 1), D(2026, 6, 30)), "Q2": (D(2026, 7, 1), D(2026, 9, 30)),
     "Q3": (D(2026, 10, 1), D(2026, 12, 31)), "Q4": (D(2027, 1, 1), D(2027, 3, 31))}
YEAR = (D(2026, 4, 1), D(2027, 3, 31))

# place: people, yearly target, [(quarter, target, fixed achieved or None)]
PLACES = {
    "Kochi": {"people": ["Hari"], "year": 130 * L, "year_start": YEAR[0],
              "quarters": [("Q1", 18 * L, 963000), ("Q2", 36 * L, 1940000), ("Q3", 45 * L, None), ("Q4", 54 * L, None)]},
    "Kannur": {"people": ["Robins"], "year": 54 * L, "year_start": D(2026, 10, 1),          # started recently: only Q3 and Q4
               "quarters": [("Q3", 18 * L, 836000), ("Q4", 36 * L, None)]},
    "Kozhikode and others": {"people": ["Hudha", "Fousan"], "year": 7 * CR, "year_start": YEAR[0],
                             "quarters": [("Q1", 180 * L, 186 * L), ("Q2", 204 * L, 206 * L), ("Q3", 240 * L, 80 * L), ("Q4", 288 * L, None)]},
}


class Command(BaseCommand):
    help = "Creates the places, their people and the sales targets."

    def handle(self, *args, **options):
        User = get_user_model()
        for place_name, info in PLACES.items():
            place, _ = Place.objects.get_or_create(name=place_name)
            for person in info["people"]:
                user = User.objects.filter(username__iexact=person).first() or User.objects.filter(first_name__iexact=person).first()
                if user is None:
                    self.stdout.write(self.style.WARNING("   %s: no account named %s (run setup_tasks first)" % (place_name, person)))
                    continue
                Profile.objects.update_or_create(user=user, defaults={"place": place})
                self.stdout.write("   %s -> %s" % (user.username, place_name))
            SalesTarget.objects.update_or_create(place=place, user=None, start_date=info["year_start"], end_date=YEAR[1],
                                                 defaults={"label": "Year", "amount": Decimal(info["year"]), "fixed_achieved": None})
            for q, amount, fixed in info["quarters"]:
                start, end = Q[q]
                SalesTarget.objects.update_or_create(place=place, user=None, start_date=start, end_date=end,
                                                     defaults={"label": q, "amount": Decimal(amount),
                                                               "fixed_achieved": Decimal(fixed) if fixed is not None else None})
            self.stdout.write(self.style.SUCCESS("%s: year + %d quarters" % (place_name, len(info["quarters"]))))
        # the earlier per-person test targets, if any, are left alone
        self.stdout.write(self.style.SUCCESS("Done."))
