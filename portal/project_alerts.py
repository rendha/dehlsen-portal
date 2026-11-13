"""Automatic follow-up for the Project progress page.  Called every day from  manage.py send_reminders.

Creates Tasks (they show in the calendar and on the person's phone) and phone alerts, once each, for:
  - KSEB deadlines: registration fee, work completion, net meter fixing, subsidy follow-up (due in 7 days, or late)       -> Fidha / Riswan
  - invoice and warranty papers to give after commissioning; the workmanship warranty about to end                         -> Fidha / Riswan
  - bank loan: first payment not received 7 days after sanction; final payment late after commissioning                     -> Payment Collection people
  - material at site worth much more than the money received (red)                                                         -> Payment Collection people + directors
  - contractor balance left after commissioning                                                                              -> Payment Collection people
It also ticks Site estimation / Design on the progress page when a Site visit / Drawing task for that customer has been marked done.
Nothing is done twice: every task carries a tag like [auto:reg:12] and is only created again if the old one is finished and the problem is still there."""
import datetime
from decimal import Decimal
from difflib import SequenceMatcher

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from . import notify
from .models import Task, TaskType
from .project_work import EDITORS, EXPOSURE_RED, BANK_LATE_DAYS, exposure, find_store_customer, kseb_clocks, warranty_list
from .models import ProjectWork

SANCTION_WAIT_DAYS = 7
CONTRACTOR_WAIT_DAYS = 3
HANDOVER_WAIT_DAYS = 3
WARRANTY_NOTICE_DAYS = 30


def _editors():
    User = get_user_model()
    q = Q()
    for n in EDITORS:
        q |= Q(username__iexact=n) | Q(first_name__iexact=n)
    return list(User.objects.filter(q, is_active=True))


def _collectors():
    tt = TaskType.objects.filter(name__iexact="Payment Collection").first()
    return list(tt.people.filter(is_active=True)) if tt else []


def _type(name):
    return TaskType.objects.get_or_create(name=name)[0]


def run(dry=False, say=print):
    from quotations import dashboard_stats as stats
    from store.models import Customer as StoreCustomer
    today = timezone.localdate()
    editors, collectors = _editors(), _collectors()
    directors = list(get_user_model().objects.filter(portal_profile__director=True, is_active=True))
    customers = list(StoreCustomer.objects.prefetch_related("lines", "payments"))
    skeys = [(stats.name_key(c.name), c) for c in customers]
    by_quotation = {c.quotation_id: c for c in customers if c.quotation_id}
    made = {"tasks": 0, "ticks": 0}

    def make(kind, w, text, due, people, push_to=(), repeat=False):
        tag = "[auto:%s:%d]" % (kind, w.pk)
        for person in people:
            qs = Task.objects.filter(assigned_to=person, details__contains=tag)
            if qs.filter(done=False).exists() or (not repeat and qs.exists()):
                continue
            made["tasks"] += 1
            say("   task -> %s: %s" % (person.username, text))
            if not dry:
                Task.objects.create(task_type=_type("Project follow-up") if person in editors else _type("Payment Collection"),
                                    details="%s - %s %s" % (w.name, text, tag),
                                    created_by=None, assigned_to=person, due_date=max(due, today) if due else today)
                try:
                    notify.send_push(person, w.name, text, "/task/mine/")
                except Exception:
                    pass
        for person in push_to:
            if not dry:
                try:
                    notify.send_push(person, w.name, text, "/progress/?tab=risk")
                except Exception:
                    pass

    open_tasks = list(Task.objects.filter(done=True, task_type__name__in=("Site visit", "Drawing")).values_list("task_type__name", "details"))

    for w in ProjectWork.objects.select_related("collection"):
        name_l = w.name.lower()
        # ticks from finished tasks
        if not dry:
            ch = False
            for tname, details in open_tasks:
                if name_l and name_l in (details or "").lower():
                    if tname == "Site visit" and not w.site_estimation:
                        w.site_estimation, ch = True, True
                    if tname == "Drawing" and not w.design:
                        w.design, ch = True, True
            if ch:
                w.save(update_fields=["site_estimation", "design"])
                made["ticks"] += 1

        # KSEB deadlines
        for c in kseb_clocks(w, today):
            if c["done"] or not (c["late"] or c["soon"]):
                continue
            when = "late by %d days" % -c["left"] if c["late"] else "due in %d days" % c["left"]
            make("kseb-" + c["label"].split()[0].lower() + c["label"].split()[-1].lower(), w, "%s %s (%s)" % (c["label"], when, c["date"].strftime("%d %b")), c["date"], editors)

        # invoice / warranty papers
        if w.commissioned and not w.handover and w.commission_date and (today - w.commission_date).days >= HANDOVER_WAIT_DAYS:
            make("handover", w, "Give the invoice and warranty papers to the customer", today, editors)
        for label, d in warranty_list(w)[:1]:
            if 0 <= (d - today).days <= WARRANTY_NOTICE_DAYS:
                make("warranty", w, "%s warranty ends on %s: offer a service visit" % (label, d.strftime("%d %b %Y")), d, editors)

        # bank loan
        if w.is_loan:
            if w.loan_sanctioned_on and not w.bank1_received_on and (today - w.loan_sanctioned_on).days >= SANCTION_WAIT_DAYS:
                make("bank1", w, "Bank first payment (Rs %d) not received %d days after sanction: please chase the bank" % (w.bank1_amount, (today - w.loan_sanctioned_on).days),
                     today, collectors, directors)
            if w.commissioned and w.commission_date and not w.bank2_received_on and (today - w.commission_date).days > BANK_LATE_DAYS:
                make("bank2", w, "Bank final payment (Rs %d) is late: plant on since %s" % (w.bank2_amount, w.commission_date.strftime("%d %b")), today, collectors, directors)

        # contractor balances
        bal = (w.electrical_amount - w.electrical_paid) + (w.structure_amount - w.structure_paid)
        if w.commissioned and bal > 0 and w.commission_date and (today - w.commission_date).days >= CONTRACTOR_WAIT_DAYS:
            make("contractor", w, "Contractor balance Rs %d to pay (electrical %s, structure %s)" % (bal, w.electrical_contractor or "-", w.structure_contractor or "-"), today, collectors)

        # material at site vs money received
        ex = exposure(w, find_store_customer(w, by_quotation, skeys, stats))
        if ex and ex["level"] == "red" and not w.commissioned:
            make("gap", w, "Material worth Rs %d is at site but only Rs %d received (gap Rs %d): collect the payment" % (ex["site"], ex["received"], ex["gap"]),
                 today, collectors, directors, repeat=True)
    say("project alerts: %d task(s) created, %d tick(s) set" % (made["tasks"], made["ticks"]))
    return made
