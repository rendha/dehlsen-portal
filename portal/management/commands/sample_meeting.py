"""Put the sample meeting (the 16 November minutes) into the portal so you can look at it:   python manage.py sample_meeting
Remove it again with:   python manage.py sample_meeting --remove
Both sample meetings have (SAMPLE) in their title, nothing else is touched."""
import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from portal.models import Meeting, MeetingAction, MeetingAttendee, MeetingPoint

TITLE = "Strategic Planning & Business Development Meeting (SAMPLE)"


class Command(BaseCommand):
    help = "Adds (or with --remove, deletes) a sample meeting with minutes and action items."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")
        parser.add_argument("--user", default="", help="username who conducts the sample meeting (default: the first superuser)")

    def handle(self, *args, **o):
        if o["remove"]:
            n, _ = Meeting.objects.filter(title__endswith="(SAMPLE)").delete()
            self.stdout.write(self.style.SUCCESS("Sample meetings removed."))
            return
        if Meeting.objects.filter(title=TITLE).exists():
            self.stdout.write("The sample is already there. Run with --remove first to add it again.")
            return
        User = get_user_model()
        me = (User.objects.filter(username=o["user"]).first() if o["user"] else None) or User.objects.filter(is_superuser=True).order_by("id").first()

        def person(name):
            """A portal user with this name if there is one, else just the typed name."""
            first = name.split()[0]
            u = User.objects.filter(Q(first_name__iexact=name) | Q(username__iexact=name) | Q(username__iexact=first) | Q(first_name__iexact=first)).first()
            return u

        def att(m, name, present=True):
            u = person(name)
            return MeetingAttendee.objects.create(meeting=m, user=u, name="" if u else name, present=present)

        def act(m, point, text, who, target, status="open", done=None, remark=""):
            u = person(who) if who else None
            MeetingAction.objects.create(meeting=m, point=point, text=text, owner_user=u, owner_name="" if (u or not who) else who,
                                         target_date=target, status=status, done_on=done, remark=remark)

        D = datetime.date
        names = ["Rijul Josoph", "Sayed Imran", "Siraj", "Mohammed Fouzan", "Shad Thaskeen"]

        # an earlier meeting with the same title, so the "Pending from last meeting" box has something to show
        old = Meeting.objects.create(title=TITLE, date=D(2026, 11, 9), time=datetime.time(19, 0), venue="Meeting Hall, Dehlsen Engineering", status="held",
                                     objective="Weekly review of the business plan.", conducted_by=me, created_by=me, prepared_by="Shad Thaskeen")
        for n in names:
            att(old, n)
        p0 = MeetingPoint.objects.create(meeting=old, title="Registration and papers", notes="Collect the company papers\nDecide the office address for the licence", position=1)
        act(old, p0, "Collect the company registration papers", "Sayed Imran", D(2026, 11, 12), "done", D(2026, 11, 11))
        act(old, p0, "Finalise the office address for the licence application", "Siraj", D(2026, 11, 13))   # not done, late

        m = Meeting.objects.create(
            title=TITLE, date=D(2026, 11, 16), time=datetime.time(19, 0), venue="Meeting Hall, Dehlsen Engineering", status="held",
            objective="The meeting was convened to discuss the strategic development of DEHLSEN ENGINEERING, focusing on electrical contractor licensing, "
                      "recruitment of qualified professionals, formation of the project management team, business operations, stakeholder "
                      "responsibilities and future expansion strategies.",
            conducted_by=me, created_by=me, follow_up_of=old, prepared_by="Shad Thaskeen", approved_by="Sayed Imran")
        for n in names:
            att(m, n)
        att(m, "Mr. Consultant (outside guest)", present=False)

        p1 = MeetingPoint.objects.create(meeting=m, position=1, title="Progress Review - Electrical Contractor Licence", notes=(
            "Discussed and decided to arrange 1 supervisor licence and 4 wireman licences\n"
            "Wireman licence: Rizwan, Sharafu, Nikhil, Vishnu\nResponsible person: Shad Thaskeen"))
        act(m, p1, "Arrange 1 supervisor licence and 4 wireman licences (Rizwan, Sharafu, Nikhil, Vishnu)", "Shad Thaskeen", D(2026, 11, 20), "progress")

        p2 = MeetingPoint.objects.create(meeting=m, position=2, title="Recruitment & Appointment of New Professionals", notes=(
            "Decided to interview and hire a Project Manager (target 23-30 Nov 26)\n"
            "Post a poster on Indeed and LinkedIn for: Project Manager, Design & Estimation Engineer, Project Engineer\n"
            "Create a check list and criteria for the interviews; decide interview stages, panels and interviewers"))
        act(m, p2, "Prepare the draft job roles for the three positions", "Shad Thaskeen", D(2026, 11, 17), "done", D(2026, 11, 17))
        act(m, p2, "Verify and finalise the job roles", "Siraj", D(2026, 11, 17), "progress")
        act(m, p2, "Prepare the poster and post it on social media", "Mohammed Fouzan", D(2026, 11, 17))
        act(m, p2, "Interview check list: personality assessment", "Sayed Imran", D(2026, 11, 20))
        act(m, p2, "Interview check list: technical assessment", "Siraj", D(2026, 11, 20))
        act(m, p2, "Interview check list: document verification and HR section", "Rijul Josoph", D(2026, 11, 20))
        act(m, p2, "Interview and hire the Project Manager", "", D(2026, 11, 30))

        p3 = MeetingPoint.objects.create(meeting=m, position=3, title="Business Scope & Stakeholder Responsibilities", notes=(
            "Shad Thaskeen: Govt. sector sales & operations management\nRijul Josoph: Govt. sector sales, business network development, CRM\n"
            "Sayed Imran: Commercial sales, operations management\nMohammed Fouzan: Operations management\nSiraj: Technical direction"))
        act(m, p3, "Consult a CA / business consultant", "Sayed Imran", D(2026, 11, 25))
        act(m, p3, "Write down the scope of the startup", "", None)

        self.stdout.write(self.style.SUCCESS("Sample added: open the portal > Meetings. Remove it with:  python manage.py sample_meeting --remove"))
