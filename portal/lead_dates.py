"""Due dates on a lead: "Site visit by" and "Quotation by".  Optional.  Each date makes a Task (Site visit / Quotation) for the person who has the lead,
so it shows in the calendar and on the phone; the card shows it (amber 2 days before, red when late); it is finished by itself when the site visit is
done / the quotation is made.  The daily job (send_reminders) sends the alerts."""
import datetime
import re

from django.utils import timezone

from . import notify
from .models import Task, TaskType

KINDS = (("site", "Site visit", "site_visit_by"), ("quote", "Quotation", "quotation_by"))
SOON_DAYS = 2


def tag(lead, kind):
    return "[lead:%d:%s]" % (lead.pk, kind)


_TAG = re.compile(r"\[lead:(\d+):(site|quote)\]")


def lead_of_task(task):
    """(lead, kind) when this task came from a lead's due date, else (None, None)."""
    from .models import Lead
    m = _TAG.search(task.details or "")
    if not m:
        return None, None
    lead = Lead.objects.prefetch_related("events").filter(pk=int(m.group(1))).first()
    return lead, m.group(2)


def parse(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip()) if (raw or "").strip() else None
    except ValueError:
        return None


def site_done(lead):
    return any(e.kind in ("visit", "site") for e in lead.events.all())


def quote_done(lead):
    return bool(lead.quotation_id or getattr(lead, "quote", None))


def is_done(lead, kind):
    return site_done(lead) if kind == "site" else quote_done(lead)


def status(lead, today=None):
    """For the card: a list of {label, date, state (done/late/soon/ok), text}."""
    today = today or timezone.localdate()
    out = []
    for kind, label, field in KINDS:
        d = getattr(lead, field)
        if not d:
            continue
        if is_done(lead, kind):
            out.append({"label": label, "date": d, "state": "done", "text": "%s done" % label})
            continue
        left = (d - today).days
        if left < 0:
            out.append({"label": label, "date": d, "state": "late", "text": "%s %d day%s late" % (label, -left, "" if left == -1 else "s")})
        elif left <= SOON_DAYS:
            out.append({"label": label, "date": d, "state": "soon", "text": "%s by %s (%s)" % (label, d.strftime("%d %b"), "today" if left == 0 else "tomorrow" if left == 1 else "in %d days" % left)})
        else:
            out.append({"label": label, "date": d, "state": "ok", "text": "%s by %s" % (label, d.strftime("%d %b"))})
    return out


def sync_tasks(lead, actor=None):
    """Make the Tasks match the lead: one open task per person who has the lead and per date; dates removed or lead lost/done = tasks removed;
    site visit done / quotation made = tasks ticked.  Safe to call any number of times."""
    people = [p for p in (lead.assigned_to, lead.assigned_to2) if p]
    for kind, label, field in KINDS:
        t = tag(lead, kind)
        date = getattr(lead, field)
        open_tasks = list(Task.objects.filter(details__contains=t, done=False))
        if not date or lead.lost or lead.done:
            for task in open_tasks:
                task.delete()
            continue
        if is_done(lead, kind):
            for task in open_tasks:
                task.done, task.done_at = True, timezone.now()
                task.save(update_fields=["done", "done_at"])
            continue
        task_type = TaskType.objects.get_or_create(name=label)[0]
        have = {task.assigned_to_id: task for task in open_tasks}
        for person in people:
            task = have.pop(person.id, None)
            text = "%s: %s%s - %s by %s %s" % ("Lead", lead.customer_name, (" (%s)" % lead.phone) if lead.phone else "", label.lower(), date.strftime("%d %b"), t)
            if task is None:
                Task.objects.create(task_type=task_type, details=text, created_by=actor or lead.entered_by, assigned_to=person, due_date=date)
                try:
                    notify.send_push(person, "%s by %s" % (label, date.strftime("%d %b")), "%s%s" % (lead.customer_name, (" - " + lead.phone) if lead.phone else ""), "/task/mine/")
                except Exception:
                    pass
            elif task.due_date != date or task.details != text:
                task.due_date, task.details = date, text
                task.save(update_fields=["due_date", "details"])
        for task in have.values():                 # a person who no longer has the lead
            task.delete()


def daily(dry=False, say=print):
    """Phone alerts: due tomorrow, due today, and 1, 3, 7 days late -> the people who have the lead; one summary line to the directors."""
    from django.contrib.auth import get_user_model
    from .models import Lead
    today = timezone.localdate()
    late = {"site": 0, "quote": 0}
    sent = 0
    for lead in Lead.objects.filter(lost=False, done=False).select_related("assigned_to", "assigned_to2", "entered_by").prefetch_related("events"):
        for kind, label, field in KINDS:
            d = getattr(lead, field)
            if not d or is_done(lead, kind):
                continue
            left = (d - today).days
            if left < 0:
                late[kind] += 1
            if left in (1, 0, -1, -3, -7):
                when = "tomorrow" if left == 1 else "today" if left == 0 else "%d day%s late" % (-left, "" if left == -1 else "s")
                for person in {u.id: u for u in (lead.assigned_to, lead.assigned_to2) if u}.values():
                    say("   lead date -> %s: %s %s (%s)" % (person.username, label, lead.customer_name, when))
                    sent += 1
                    if not dry:
                        try:
                            notify.send_push(person, "%s %s" % (label, when), lead.customer_name, "/leads/")
                        except Exception:
                            pass
        if not dry:
            sync_tasks(lead)
    if late["site"] or late["quote"]:
        body = "%d site visit%s and %d quotation%s overdue." % (late["site"], "" if late["site"] == 1 else "s", late["quote"], "" if late["quote"] == 1 else "s")
        for person in get_user_model().objects.filter(portal_profile__director=True, is_active=True):
            say("   alert -> %s: Leads overdue - %s" % (person.username, body))
            if not dry:
                try:
                    notify.send_push(person, "Leads overdue", body, "/leads/")
                except Exception:
                    pass
    return sent
