"""py manage.py send_reminders  -  the daily automatic reminders.  Run it once a day (Render: a Cron Job at about 9 am).  Safe to run twice a day.

1. A lead that nobody touched for 3, 7, 14, 21 or 30 days gets a phone alert to the person who has it (and the person who entered it).
2. A lead with a quotation and no news for 3 days gets a "Quotation" follow-up task for the person who has it (once per lead).
3. The directors get one summary alert: new leads, quotations made yesterday, leads waiting, tasks overdue.

Nothing is sent for lost leads or leads already won.  It only uses phone alerts (push) and Tasks; no WhatsApp account is needed.
--dry-run  shows what it WOULD do and sends nothing.
"""
import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from portal import notify
from portal.models import Lead, Profile, Task, TaskType

IDLE_DAYS = (3, 7, 14, 21, 30)          # remind on exactly these idle days, so nobody is nagged every day
QUOTE_WAIT_DAYS = 3


def last_activity(lead):
    last = lead.events.order_by("-created_at").first()
    return last.created_at if last else lead.created_at


class Command(BaseCommand):
    help = "Daily reminders: idle leads, quotation follow-ups, director summary."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        now = timezone.now()
        today = timezone.localdate()
        sent = {"idle": 0, "quote": 0, "summary": 0}

        def push(user, title, body, url):
            if user is None:
                return
            self.stdout.write("   alert -> %s: %s - %s" % (user.username, title, body))
            if not dry:
                try:
                    notify.send_push(user, title, body, url)
                except Exception:
                    pass

        open_leads = [l for l in Lead.objects.filter(lost=False, done=False).select_related("entered_by", "assigned_to", "assigned_to2")
                      if not l.events.filter(kind="won").exists()]

        # 1. idle leads
        for lead in open_leads:
            idle = (now - last_activity(lead)).days
            if idle in IDLE_DAYS:
                for person in {u.id: u for u in (lead.assigned_to, lead.assigned_to2, lead.entered_by) if u}.values():
                    push(person, "Lead waiting: %s" % lead.customer_name, "No news for %d days. Please follow up." % idle, reverse("leads"))
                sent["idle"] += 1

        # 2. quotation sent, no answer
        quote_type = TaskType.objects.filter(name__iexact="Quotation").first()
        for lead in open_leads:
            if not lead.quotation_id or quote_type is None:
                continue
            quoted = lead.events.filter(kind__in=("quote", "quoted")).order_by("-created_at").first()
            since = quoted.created_at if quoted else None
            if since is None or (now - last_activity(lead)).days < QUOTE_WAIT_DAYS or last_activity(lead) > since + datetime.timedelta(minutes=5):
                continue
            person = lead.assigned_to or lead.entered_by
            details = "Follow up: %s (%s) - the quotation has had no answer for %d days." % (lead.customer_name, lead.phone or "no phone", (now - since).days)
            if Task.objects.filter(task_type=quote_type, assigned_to=person, details__startswith="Follow up: %s" % lead.customer_name, done=False).exists():
                continue
            self.stdout.write("   task -> %s: %s" % (person.username, details))
            if not dry:
                task = Task.objects.create(task_type=quote_type, details=details, created_by=lead.entered_by, assigned_to=person, due_date=today)
                try:
                    notify.send_push(person, "Quotation follow-up", details, "/task/mine/")
                except Exception:
                    pass
            sent["quote"] += 1

        # 3. director summary
        yesterday = now - datetime.timedelta(days=1)
        new_leads = Lead.objects.filter(created_at__gte=yesterday).count()
        quotes = 0
        try:
            from quotations.models import Quotation
            quotes = Quotation.objects.filter(date__gte=yesterday.date()).count()
        except Exception:
            pass
        waiting = sum(1 for l in open_leads if (now - last_activity(l)).days >= 7)
        overdue = Task.objects.filter(done=False, due_date__lt=today).count()
        body = "%d new lead%s, %d quotation%s yesterday. %d lead%s waiting 7+ days, %d task%s overdue." % (
            new_leads, "" if new_leads == 1 else "s", quotes, "" if quotes == 1 else "s", waiting, "" if waiting == 1 else "s",
            overdue, "" if overdue == 1 else "s")
        User = get_user_model()
        directors = list(User.objects.filter(portal_profile__director=True, is_active=True))
        for person in directors:
            push(person, "Daily summary", body, "/")
            sent["summary"] += 1

        # 4. project follow-up: KSEB deadlines, bank loans, payment gaps, warranty (see portal/project_alerts.py)
        try:
            from portal import project_alerts
            project_alerts.run(dry, self.stdout.write)
        except Exception as error:
            self.stdout.write("   project alerts skipped: %s" % error)

        self.stdout.write(self.style.SUCCESS("%sidle leads: %d, quotation follow-ups: %d, summaries: %d" % ("(dry run) " if dry else "", sent["idle"], sent["quote"], sent["summary"])))
