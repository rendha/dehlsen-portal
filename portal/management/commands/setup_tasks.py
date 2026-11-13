"""py manage.py setup_tasks  -  creates the six tasks and the people who do each one (safe to run again: it adds what is missing).

A person is found by username or first name (any capitals).  Run  import_users  first so the real logins exist.  A name that is not found gets
a NEW account:  username = the name in small letters,  password = the name in small letters + "dehlsen"   (Hudha -> hudha / hudhadehlsen).
--no-create only LISTS such names instead.  The new accounts are printed at the end.
Change the people later in /admin/ > Task types."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.models import TaskPerson, TaskType

# task -> [(person, note shown next to the name)]
TASKS = {
    "Quotation": [("Siraj", ""), ("Fousan", ""), ("Hudha", "")],
    "Site visit": [("Riswan", ""), ("Junaid", ""), ("Ziyad", ""), ("Aswanth", "")],
    "Drawing": [("Siraj", ""), ("Fidha", "")],
    "Payment Collection": [("Anoop", "")],
    "Cleaning and Services": [("Fidha", "")],
    "Leads": [("Hari", "Ernakulam"), ("Robins", "Kannur"), ("Hudha", "Kozhikode & others"), ("Fousan", "Kozhikode & others")],
}


# people who get a login but are not on any task yet (add them to tasks in /admin/ > Task types)
EXTRA_PEOPLE = ["Anupama", "Satheesh", "Rijul"]
RESET_PASSWORDS = {"Imran": "imrandehlsen"}          # a forgotten password: set again to this every time the command runs
DIRECTORS = ["Imran", "Rijul"]          # see the sales dashboard of everybody, and can bring sales too

# other spellings -> the username already in the apps (not needed now: the names above use the usernames' spelling)
ALIASES = {}


class Command(BaseCommand):
    help = "Creates the six tasks and links the people who do them (people must already have an account, so the spelling is the login's)."

    def add_arguments(self, parser):
        parser.add_argument("--no-create", action="store_true", help="do not make accounts for names that are not found; only list them")

    def find_user(self, name):
        User = get_user_model()
        for candidate in (name, ALIASES.get(name.lower())):
            if not candidate:
                continue
            found = User.objects.filter(username__iexact=candidate).first() or User.objects.filter(first_name__iexact=candidate).first()
            if found:
                if candidate != name:
                    self.stdout.write("   (%s is the existing account %s)" % (name, found.username))
                return found
        return None

    def handle(self, *args, **options):
        import difflib
        User = get_user_model()
        known = list(User.objects.values_list("username", flat=True))
        missing = {}
        created = []
        for task_name, people in TASKS.items():
            task_type, made = TaskType.objects.get_or_create(name=task_name)
            self.stdout.write("%s task %s" % (task_name, "created" if made else "already there"))
            for name, note in people:
                user = self.find_user(name)
                if user is None and not options["no_create"]:
                    login = name.lower().replace(" ", "")
                    user = User(username=login, first_name=name)
                    user.set_password(login + "dehlsen")
                    user.save()
                    known.append(user.username)
                    created.append((login, login + "dehlsen"))
                    self.stdout.write("   %s: new account made" % name)
                if user is None:
                    missing[name] = difflib.get_close_matches(name.lower(), [k.lower() for k in known], n=3, cutoff=0.6)
                    self.stdout.write("   %s: NOT FOUND (left out for now)" % name)
                    continue
                row, linked = TaskPerson.objects.get_or_create(task_type=task_type, user=user, defaults={"note": note})
                if not linked and note and not row.note:
                    row.note = note
                    row.save(update_fields=["note"])
                self.stdout.write("   %s%s%s" % (user.username, " (%s)" % note if note else "", "" if linked else "  (already there)"))
        for name in EXTRA_PEOPLE:
            if self.find_user(name) is None and not options["no_create"]:
                login = name.lower().replace(" ", "")
                user = User(username=login, first_name=name)
                user.set_password(login + "dehlsen")
                user.save()
                created.append((login, login + "dehlsen"))
                self.stdout.write("%s: new account made (not on any task yet)" % name)
        from portal.models import Profile
        for name in DIRECTORS:
            user = self.find_user(name)
            if user is not None:
                Profile.objects.update_or_create(user=user, defaults={"director": True})
                self.stdout.write("%s: marked as director" % user.username)
        for name, password in ({} if options["no_create"] else RESET_PASSWORDS).items():     # --no-create never touches a password
            user = self.find_user(name)
            if user is None:
                user = User(username=name.lower(), first_name=name)
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS("%s: login is %s / %s" % (name, user.username, password)))
        if created:
            self.stdout.write(self.style.WARNING("\nNEW ACCOUNTS (username / password):"))
            for login, password in created:
                self.stdout.write("   %-12s %s" % (login, password))
        if missing:
            self.stdout.write(self.style.WARNING("\nThese people have no account with that name, so they are not on their tasks yet:"))
            for name, close in missing.items():
                self.stdout.write("   %-10s %s" % (name, ("maybe: " + ", ".join(close)) if close else "no similar username"))
            self.stdout.write("Fix: run  import_users  first (to bring the real logins), or change the name in TASKS at the top of "
                              "portal/management/commands/setup_tasks.py to the login's spelling, or leave out --no-create to make them.")
        self.stdout.write(self.style.SUCCESS("\nDone."))
