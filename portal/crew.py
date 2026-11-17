"""Crew plan: which team goes to which site on which day, with a month calendar.  Riswan, Fidha, superusers and directors add; everybody logged in can read."""
import calendar
import datetime
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CrewAssignment, ProjectWork
from .project_work import can_edit


# The contractor lists of the Project List workbook (Settings sheet).  Anyone else is typed under "Other".
CONTRACTORS = [("Electrical", ["AFSAL", "SAHAD", "MUSIN", "JIJO", "DEHLSEN"]), ("Structure", ["MIDHUN", "ABID", "SADIK", "SHIVAPRASAD"])]


def _date(s, default=None):
    try:
        return datetime.date.fromisoformat((s or "").strip())
    except ValueError:
        return default


def _match(site):
    s = (site or "").strip()
    if not s:
        return None
    p = ProjectWork.objects.filter(name__iexact=s).first()
    if p:
        return p
    qs = ProjectWork.objects.filter(name__icontains=s)
    return qs.first() if qs.count() == 1 else None


def _back(day):
    return redirect(reverse("crew") + "?d=" + day.isoformat())


def whatsapp_text(day, items):
    """The same list Riswan used to type, ready to paste or send."""
    live = [a for a in items if a.status != "cancelled"]
    if not live:
        return ""
    out = ["*Work plan - " + day.strftime("%A, %d %b %Y") + "*"]
    by = {}
    for a in live:
        by.setdefault(a.work, []).append(a)
    n = 0
    for work, rows in by.items():
        out.append("")
        out.append("*" + work + "*")
        for a in rows:
            n += 1
            place = a.project.location if a.project_id and a.project.location else ""
            line = f"{n}. {a.team} - {a.site_name}" + (f" ({place})" if place else "")
            if a.note:
                line += f" [{a.note}]"
            out.append(line)
    return "\n".join(out)


def crew(request):
    today = timezone.localdate()
    sel = _date(request.GET.get("d"))
    ym = request.GET.get("ym") or ""
    if sel:
        y, m = sel.year, sel.month
    elif len(ym) == 7 and ym[4] == "-" and ym[:4].isdigit() and ym[5:].isdigit() and 1 <= int(ym[5:]) <= 12:
        y, m = int(ym[:4]), int(ym[5:])
    else:
        sel = today
        y, m = today.year, today.month
    first = datetime.date(y, m, 1)
    prev_m = (first - datetime.timedelta(days=1)).replace(day=1)
    next_m = (first + datetime.timedelta(days=32)).replace(day=1)

    weeks_dates = calendar.Calendar(6).monthdatescalendar(y, m)
    lo, hi = weeks_dates[0][0], weeks_dates[-1][-1]
    counts = {r["date"]: r["n"] for r in CrewAssignment.objects.filter(date__range=(lo, hi)).exclude(status="cancelled").values("date").annotate(n=Count("id"))}
    weeks = [[{"date": d, "n": counts.get(d, 0), "in": d.month == m, "today": d == today, "sel": d == sel} for d in wk] for wk in weeks_dates]

    items = list(CrewAssignment.objects.filter(date=sel).select_related("project")) if sel else []
    editor = can_edit(request.user)
    ctx = {
        "weeks": weeks, "month": first, "prev": prev_m.strftime("%Y-%m"), "next": next_m.strftime("%Y-%m"),
        "sel": sel, "today": today, "tomorrow": today + datetime.timedelta(days=1), "items": items, "editor": editor,
        "wa": whatsapp_text(sel, items) if sel else "", "month_total": sum(counts.get(d, 0) for d in counts if d.month == m),
    }
    ctx["wa_url"] = "https://wa.me/?text=" + quote(ctx["wa"]) if ctx["wa"] else ""
    if editor:
        ctx["works"] = [w for w, _l in CrewAssignment.WORKS]
        ctx["contractors"] = CONTRACTORS
        ctx["teams"] = list(CrewAssignment.objects.order_by("-id").values_list("team", flat=True).distinct()[:80])
        ctx["sites"] = list(ProjectWork.objects.order_by("name").values_list("name", "location"))
    return render(request, "portal/crew.html", ctx)


@require_POST
def crew_add(request):
    if not can_edit(request.user):
        messages.error(request, "Only Riswan, Fidha and the directors can plan the crew.")
        return redirect("crew")
    day = _date(request.POST.get("date"), timezone.localdate())
    team = request.POST.get("team", "").strip()
    if team == "__other__" or not team:
        team = request.POST.get("team_other", "").strip()
    site = request.POST.get("site", "").strip()
    if not team or not site:
        messages.error(request, "Choose who is going (or type a name under Other) and which site.")
        return _back(day)
    proj = _match(site)
    CrewAssignment.objects.create(
        date=day, team=team[:200], work=request.POST.get("work") or "Other", project=proj,
        site="" if proj else site[:200], note=request.POST.get("note", "").strip()[:300], created_by=request.user)
    messages.success(request, f"Added: {team} to {proj.name if proj else site}.")
    return _back(day)


@require_POST
def crew_status(request, pk):
    a = get_object_or_404(CrewAssignment, pk=pk)
    if can_edit(request.user):
        s = request.POST.get("status")
        if s in {k for k, _l in CrewAssignment.STATUS}:
            a.status = s
            a.save(update_fields=["status"])
    return _back(a.date)


@require_POST
def crew_delete(request, pk):
    a = get_object_or_404(CrewAssignment, pk=pk)
    day = a.date
    if can_edit(request.user):
        a.delete()
        messages.success(request, "Removed.")
    return _back(day)


@require_POST
def crew_copy(request, pk):
    """Same team, same site, another day (default: the next day) - for work that takes more than one day."""
    a = get_object_or_404(CrewAssignment, pk=pk)
    if not can_edit(request.user):
        return _back(a.date)
    day = _date(request.POST.get("date"), a.date + datetime.timedelta(days=1))
    CrewAssignment.objects.create(date=day, team=a.team, work=a.work, project=a.project, site=a.site, note=a.note, created_by=request.user)
    messages.success(request, "Repeated on " + day.strftime("%a %d %b") + ".")
    return _back(day)
