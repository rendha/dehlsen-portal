"""Lead report: daily, weekly and monthly, like the quotation report.   /leads/report/   ?p=day|week|month   &date=2026-11-23   &month=2026-11   &from=..&to=..   &csv=1
What it counts (everything inside the period):
  New leads (by priority and by person who entered them) - calls, site visits, quotations linked, handed over, WON and LOST (from the history of each lead).
  Heads (the same four people who see all leads) see everybody; everyone else sees only the leads he entered or was given.
  The pipeline today (open leads, stale for 7+ days, site visit / quotation date passed) is shown under the numbers."""
import csv
import datetime
from collections import OrderedDict

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Lead, LeadEvent
from .views import _is_lead_head, _person

KINDS = [("call", "Calls"), ("visit", "Site visits"), ("quote", "Quotations"), ("passed", "Handed over"), ("won", "Won"), ("lost", "Lost")]


def _day(text, fallback):
    try:
        return datetime.datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return fallback


def _month(text, fallback):
    try:
        return datetime.datetime.strptime((text or "").strip(), "%Y-%m").date().replace(day=1)
    except ValueError:
        return fallback


def _add_months(first, n):
    i = first.year * 12 + first.month - 1 + n
    return datetime.date(i // 12, i % 12 + 1, 1)


def _bounds(first, last):
    tz = timezone.get_current_timezone()
    return (datetime.datetime.combine(first, datetime.time.min, tzinfo=tz), datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz))


def _period(request, today):
    """-> kind, first day, last day, previous (first, last), the label, links (previous, next)"""
    kind = request.GET.get("p") if request.GET.get("p") in ("day", "week", "month") else "day"
    if kind == "month":
        first = _month(request.GET.get("month"), today.replace(day=1))
        last = _add_months(first, 1) - datetime.timedelta(days=1)
        before = (_add_months(first, -1), first - datetime.timedelta(days=1))
        label = first.strftime("%B %Y")
        prev_q = "?p=month&month=%s" % _add_months(first, -1).strftime("%Y-%m")
        next_q = "?p=month&month=%s" % _add_months(first, 1).strftime("%Y-%m") if _add_months(first, 1) <= today else ""
    elif kind == "week":
        anchor = _day(request.GET.get("date"), today)
        first = anchor - datetime.timedelta(days=anchor.weekday())
        last = first + datetime.timedelta(days=6)
        before = (first - datetime.timedelta(days=7), first - datetime.timedelta(days=1))
        label = "%s to %s" % (first.strftime("%d %b"), last.strftime("%d %b %Y"))
        prev_q = "?p=week&date=%s" % (first - datetime.timedelta(days=7)).isoformat()
        next_q = "?p=week&date=%s" % (first + datetime.timedelta(days=7)).isoformat() if first + datetime.timedelta(days=7) <= today else ""
    else:
        first = _day(request.GET.get("from") or request.GET.get("date"), today)
        last = _day(request.GET.get("to") or request.GET.get("date"), first)
        if last < first:
            first, last = last, first
        n = (last - first).days + 1
        before = (first - datetime.timedelta(days=n), first - datetime.timedelta(days=1))
        label = first.strftime("%A, %d %B %Y") if n == 1 else "%s to %s" % (first.strftime("%d %b"), last.strftime("%d %b %Y"))
        prev_q = "?p=day&from=%s&to=%s" % (before[0].isoformat(), before[1].isoformat())
        nxt = last + datetime.timedelta(days=1)
        next_q = "?p=day&from=%s&to=%s" % (nxt.isoformat(), (nxt + datetime.timedelta(days=n - 1)).isoformat()) if nxt <= today else ""
    return kind, first, last, before, label, prev_q, next_q


def _count(scope, first, last):
    """The headline numbers for one period (so this period can be compared with the one before)."""
    lo, hi = _bounds(first, last)
    new = scope.filter(created_at__gte=lo, created_at__lt=hi)
    ev = LeadEvent.objects.filter(lead__in=scope, created_at__gte=lo, created_at__lt=hi)
    out = {"new": new.count()}
    for k, _l in KINDS:
        out[k] = ev.filter(kind=k).values("lead_id").distinct().count()
    return out


def _scope(user):
    base = Lead.objects.all()
    if _is_lead_head(user):
        return base, True
    return base.filter(Q(entered_by=user) | Q(assigned_to=user) | Q(assigned_to2=user)), False


def report(request):
    today = timezone.localdate()
    scope, head = _scope(request.user)
    who = request.GET.get("who", "")
    if head and who.isdigit():
        scope = scope.filter(Q(entered_by_id=int(who)) | Q(assigned_to_id=int(who)) | Q(assigned_to2_id=int(who)))
    kind, first, last, before, label, prev_q, next_q = _period(request, today)
    lo, hi = _bounds(first, last)

    new_leads = list(scope.filter(created_at__gte=lo, created_at__lt=hi).select_related("entered_by", "assigned_to").order_by("-created_at"))
    events = list(LeadEvent.objects.filter(lead__in=scope, created_at__gte=lo, created_at__lt=hi, kind__in=[k for k, _l in KINDS]).select_related("lead", "by").order_by("-created_at"))

    people = OrderedDict()

    def row(user):
        key = user.id if user else 0
        return people.setdefault(key, dict({"name": _person(user) if user else "Nobody", "new": 0, "hot": 0, "medium": 0, "cold": 0}, **{k: 0 for k, _l in KINDS}))

    for l in new_leads:
        r = row(l.entered_by)
        r["new"] += 1
        r[l.priority] += 1
    seen = set()
    for e in events:
        if (e.by_id, e.lead_id, e.kind) in seen:                 # one person doing the same thing twice on one lead counts once
            continue
        seen.add((e.by_id, e.lead_id, e.kind))
        row(e.by)[e.kind] += 1
    people_rows = sorted(people.values(), key=lambda r: (-r["won"], -r["new"], -r["call"], r["name"].lower()))

    # the day-by-day breakdown for a week or a month
    days = []
    if (last - first).days >= 1:
        by_day = {}
        for l in new_leads:
            by_day.setdefault(timezone.localtime(l.created_at).date(), {"new": 0, "won": 0, "lost": 0})["new"] += 1
        done_day = set()
        for e in events:
            if e.kind in ("won", "lost") and (e.lead_id, e.kind) not in done_day:
                done_day.add((e.lead_id, e.kind))
                by_day.setdefault(timezone.localtime(e.created_at).date(), {"new": 0, "won": 0, "lost": 0})[e.kind] += 1
        d = first
        top = max([v["new"] for v in by_day.values()] + [1])
        while d <= min(last, today):
            v = by_day.get(d, {"new": 0, "won": 0, "lost": 0})
            days.append({"date": d, "new": v["new"], "won": v["won"], "lost": v["lost"], "bar": int(100 * v["new"] / top)})
            d += datetime.timedelta(days=1)

    now, prev = _count(scope, first, last), _count(scope, *before)
    cards = [("New leads", "new")] + [(l, k) for k, l in KINDS]
    stats = []
    for name, k in cards:
        diff = now[k] - prev[k]
        stats.append({"name": name, "value": now[k], "diff": diff, "prev": prev[k]})
    decided = now["won"] + now["lost"]
    win_rate = "%d%%" % round(100 * now["won"] / decided) if decided else "-"

    won_list = _once([e for e in events if e.kind == "won"])
    lost_list = _once([e for e in events if e.kind == "lost"])

    # the pipeline today
    open_now = scope.filter(done=False, lost=False)
    stale = open_now.filter(created_at__lt=timezone.now() - datetime.timedelta(days=7)).count()
    visited = set(LeadEvent.objects.filter(lead__in=open_now, kind="visit").values_list("lead_id", flat=True))
    visit_late = [l for l in open_now.filter(site_visit_by__lt=today) if l.id not in visited]
    quote_late = list(open_now.filter(quotation_by__lt=today, quotation_id__isnull=True))
    pipeline = {"open": open_now.count(), "hot": open_now.filter(priority="hot").count(), "medium": open_now.filter(priority="medium").count(), "cold": open_now.filter(priority="cold").count(),
                "stale": stale, "visit_late": visit_late, "quote_late": quote_late}

    if request.GET.get("csv"):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="leads-%s-to-%s.csv"' % (first.isoformat(), last.isoformat())
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["Lead ID", "Created", "Customer", "Phone", "Place", "Priority", "Entered by", "Assigned to", "Type", "System", "Status"])
        for l in new_leads:
            w.writerow([l.lead_no, timezone.localtime(l.created_at).strftime("%Y-%m-%d %H:%M"), l.customer_name, l.phone, l.area, l.get_priority_display(), _person(l.entered_by),
                        _person(l.assigned_to) if l.assigned_to else "", ", ".join(l.type_chips[:2]), l.system_label, "Lost" if l.lost else ("Done" if l.done else "Open")])
        w.writerow([])
        w.writerow(["Activity", "When", "Lead ID", "Customer", "Who", "What"])
        for e in events:
            w.writerow([dict(KINDS)[e.kind], timezone.localtime(e.created_at).strftime("%Y-%m-%d %H:%M"), e.lead.lead_no, e.lead.customer_name, _person(e.by) if e.by else "", e.text])
        return resp

    from django.contrib.auth import get_user_model
    staff = []
    if head:
        U = get_user_model()
        ids = set(Lead.objects.values_list("entered_by_id", flat=True)) | set(Lead.objects.exclude(assigned_to=None).values_list("assigned_to_id", flat=True))
        staff = sorted(((u.id, _person(u)) for u in U.objects.filter(id__in=ids)), key=lambda t: t[1].lower())
    return render(request, "portal/lead_report.html", {
        "kind": kind, "first": first, "last": last, "label": label, "today": today, "prev_q": prev_q, "next_q": next_q, "who": who, "staff": staff, "head": head,
        "stats": stats, "win_rate": win_rate, "people": people_rows, "days": days, "new_leads": new_leads, "won_list": won_list, "lost_list": lost_list,
        "pipeline": pipeline, "kinds": KINDS, "month": first.strftime("%Y-%m"), "events": events[:200],
    })


def _once(events):
    """One line per lead (a lead can be marked won and then undone and won again)."""
    out, seen = [], set()
    for e in events:
        if e.lead_id in seen:
            continue
        seen.add(e.lead_id)
        out.append({"lead": e.lead, "when": timezone.localtime(e.created_at), "by": _person(e.by) if e.by else "", "text": e.text})
    return out
