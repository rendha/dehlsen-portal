"""Meetings: schedule a meeting, write its minutes (discussion points and decisions), list who attends, and keep action items with a
responsible person and a target date so that what was said in a meeting can be checked later.  The conducting person edits the minutes;
the responsible person can tick his own items."""
import datetime
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Meeting, MeetingAction, MeetingAttendee, MeetingPoint


def _date(s, default=None):
    try:
        return datetime.date.fromisoformat((s or "").strip())
    except ValueError:
        return default


def _time(s):
    try:
        return datetime.time.fromisoformat((s or "").strip()) if (s or "").strip() else None
    except ValueError:
        return None


def _name(u):
    return u.get_full_name() or u.get_username()


def _users():
    return sorted(get_user_model().objects.filter(is_active=True), key=lambda u: _name(u).lower())


def _safe_next(request, default):
    nxt = request.POST.get("next") or ""
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def open_actions_of(user):
    """Open action items given to this person (used for the badge on the Meetings button)."""
    return MeetingAction.objects.filter(owner_user=user, status__in=("open", "progress")).exclude(meeting__status="cancelled")


def _stats(actions):
    total = len([a for a in actions if a.status != "dropped"])
    done = len([a for a in actions if a.status == "done"])
    return {"total": total, "done": done, "open": total - done, "pct": int(round(100 * done / total)) if total else 0,
            "overdue": len([a for a in actions if a.overdue])}


def meetings(request):
    today = timezone.localdate()
    rows = []
    for m in Meeting.objects.prefetch_related("actions", "attendees").all()[:300]:
        s = _stats(list(m.actions.all()))
        rows.append({"m": m, "s": s, "n_att": m.attendees.count()})
    upcoming = sorted([r for r in rows if r["m"].date >= today and r["m"].status != "cancelled"], key=lambda r: (r["m"].date, r["m"].time or datetime.time(0)))
    past = [r for r in rows if r not in upcoming]
    mine = list(open_actions_of(request.user).select_related("meeting").order_by("target_date", "id"))
    return render(request, "portal/meetings.html", {"upcoming": upcoming, "past": past, "mine": mine, "today": today})


def meeting_items(request):
    """Every action item still open, in all meetings: the follow-up list."""
    who = request.GET.get("who") == "me"
    qs = MeetingAction.objects.filter(status__in=("open", "progress")).exclude(meeting__status="cancelled").select_related("meeting", "owner_user")
    if who:
        qs = qs.filter(owner_user=request.user)
    items = sorted(qs, key=lambda a: (a.target_date is None, a.target_date or datetime.date.max, a.id))
    return render(request, "portal/meeting_items.html", {"items": items, "who": who, "today": timezone.localdate(),
                                                         "overdue": len([a for a in items if a.overdue])})


def meeting_new(request):
    if request.method == "POST":
        P = request.POST
        title = (P.get("title") or "").strip()
        day = _date(P.get("date"))
        if not title or not day:
            messages.error(request, "Give the meeting a title and a date.")
            return redirect("meeting_new")
        User = get_user_model()
        cond = User.objects.filter(pk=P.get("conducted_by")).first() if (P.get("conducted_by") or "").isdigit() else request.user
        prev = Meeting.objects.filter(pk=P.get("follow_up_of")).first() if (P.get("follow_up_of") or "").isdigit() else None
        if prev is None:     # a repeating meeting: follow up the last one with the same title
            prev = Meeting.objects.filter(title__iexact=title, date__lt=day).order_by("-date", "-id").first()
        m = Meeting.objects.create(
            title=title[:200], date=day, time=_time(P.get("time")), venue=(P.get("venue") or "").strip()[:200],
            objective=(P.get("objective") or "").strip(), conducted_by=cond, follow_up_of=prev,
            prepared_by=_name(cond) if cond else "", created_by=request.user)
        ids = [int(x) for x in P.getlist("attendees") if x.isdigit()]
        for u in User.objects.filter(pk__in=ids):
            MeetingAttendee.objects.create(meeting=m, user=u)
        for line in (P.get("others") or "").splitlines():
            if line.strip():
                MeetingAttendee.objects.create(meeting=m, name=line.strip()[:120])
        messages.success(request, "Meeting scheduled.")
        return redirect("meeting", pk=m.pk)
    prev = list(Meeting.objects.order_by("-date")[:60])
    return render(request, "portal/meeting_new.html", {"users": _users(), "me": request.user, "prev": prev,
                                                       "today": timezone.localdate()})


def whatsapp_text(m, actions):
    out = ["*" + m.title + "*", m.date.strftime("%A, %d %b %Y") + (m.time.strftime(", %I:%M %p").replace(" 0", " ") if m.time else "") +
           ((" - " + m.venue) if m.venue else "")]
    if m.attendees.exists():
        out += ["", "Attending: " + ", ".join(a.label for a in m.attendees.all())]
    live = [a for a in actions if a.status != "dropped"]
    if live:
        out += ["", "*Action items*"]
        for n, a in enumerate(live, 1):
            mark = {"done": "(done)", "progress": "(in progress)"}.get(a.status, "")
            out.append("%d. %s - %s%s %s" % (n, a.text, a.owner_label or "unassigned",
                                              (", by " + a.target_date.strftime("%d-%m-%y")) if a.target_date else "", mark))
    return "\n".join(out)


def meeting(request, pk):
    m = get_object_or_404(Meeting.objects.select_related("conducted_by", "follow_up_of"), pk=pk)
    actions = list(m.actions.select_related("owner_user", "point"))
    points = list(m.points.all())
    for p in points:
        p.rows = [a for a in actions if a.point_id == p.id]
    loose = [a for a in actions if a.point_id is None]
    pending = []
    if m.follow_up_of_id:
        pending = list(m.follow_up_of.actions.filter(status__in=("open", "progress")).select_related("owner_user"))
    editor = m.can_edit(request.user)
    wa = whatsapp_text(m, actions)
    ctx = {"m": m, "points": points, "loose": loose, "attendees": list(m.attendees.select_related("user")), "pending": pending, "editor": editor,
           "s": _stats(actions), "today": timezone.localdate(), "wa": wa, "wa_url": "https://wa.me/?text=" + quote(wa),
           "me_id": request.user.id,
           "pdf_name": _pdf_name(m), "STATUS": MeetingAction.STATUS}
    if editor:
        have = {a.user_id for a in ctx["attendees"] if a.user_id}
        ctx["more_users"] = [u for u in _users() if u.pk not in have]
        ctx["users"] = _users()
        ctx["meeting_status"] = Meeting.STATUS
    return render(request, "portal/meeting.html", ctx)


def _owner(P, m):
    """The responsible person chosen on a form: an attendee, or a typed name."""
    choice = P.get("owner") or ""
    if choice.isdigit():
        a = m.attendees.filter(pk=choice).first()
        if a:
            return a.user, ("" if a.user_id else a.name)
    if choice == "__other__" and (P.get("owner_other") or "").strip():
        return None, P.get("owner_other").strip()[:120]
    return None, ""


@require_POST
def meeting_do(request, pk):
    m = get_object_or_404(Meeting, pk=pk)
    back = redirect("meeting", pk=m.pk)
    if not m.can_edit(request.user):
        messages.error(request, "Only the person conducting this meeting can change its minutes.")
        return back
    P, op = request.POST, request.POST.get("op")
    User = get_user_model()
    if op == "edit":
        title = (P.get("title") or "").strip()
        if title:
            m.title = title[:200]
        m.date = _date(P.get("date"), m.date)
        m.time = _time(P.get("time"))
        m.venue = (P.get("venue") or "").strip()[:200]
        m.objective = (P.get("objective") or "").strip()
        if P.get("status") in {k for k, _l in Meeting.STATUS}:
            m.status = P.get("status")
        if (P.get("conducted_by") or "").isdigit():
            m.conducted_by = User.objects.filter(pk=P.get("conducted_by")).first() or m.conducted_by
        m.prepared_by = (P.get("prepared_by") or "").strip()[:120]
        m.approved_by = (P.get("approved_by") or "").strip()[:120]
        m.save()
        messages.success(request, "Saved.")
    elif op == "att_add":
        if (P.get("user") or "").isdigit():
            u = User.objects.filter(pk=P.get("user")).first()
            if u and not m.attendees.filter(user=u).exists():
                MeetingAttendee.objects.create(meeting=m, user=u)
        for line in (P.get("others") or "").splitlines():
            if line.strip():
                MeetingAttendee.objects.create(meeting=m, name=line.strip()[:120])
    elif op == "att_del":
        m.attendees.filter(pk=P.get("id")).delete()
    elif op == "attendance":
        present = {int(x) for x in P.getlist("present") if x.isdigit()}
        for a in m.attendees.all():
            a.present = a.pk in present
            a.save(update_fields=["present"])
        if m.status == "scheduled":
            m.status = "held"
            m.save(update_fields=["status"])
        messages.success(request, "Attendance saved.")
    elif op == "point_add":
        t = (P.get("title") or "").strip()
        if t:
            MeetingPoint.objects.create(meeting=m, title=t[:200], notes=(P.get("notes") or "").strip(), position=m.points.count() + 1)
    elif op == "point_edit":
        p = m.points.filter(pk=P.get("id")).first()
        if p and (P.get("title") or "").strip():
            p.title, p.notes = P.get("title").strip()[:200], (P.get("notes") or "").strip()
            p.save()
    elif op == "point_del":
        m.points.filter(pk=P.get("id")).delete()
    elif op in ("action_add", "action_edit"):
        text = (P.get("text") or "").strip()
        if text:
            u, nm = _owner(P, m)
            if op == "action_add":
                pt = m.points.filter(pk=P.get("point")).first() if (P.get("point") or "").isdigit() else None
                MeetingAction.objects.create(meeting=m, point=pt, text=text[:500], owner_user=u, owner_name=nm, target_date=_date(P.get("target_date")))
            else:
                a = m.actions.filter(pk=P.get("id")).first()
                if a:
                    a.text, a.owner_user, a.owner_name, a.target_date = text[:500], u, nm, _date(P.get("target_date"))
                    a.save()
        else:
            messages.error(request, "Write what has to be done.")
    elif op == "action_del":
        m.actions.filter(pk=P.get("id")).delete()
    elif op == "delete":
        m.delete()
        messages.success(request, "Meeting deleted.")
        return redirect("meetings")
    return back


@require_POST
def action_status(request, pk):
    a = get_object_or_404(MeetingAction.objects.select_related("meeting"), pk=pk)
    default = reverse("meeting", args=[a.meeting_id])
    if a.meeting.can_edit(request.user) or (a.owner_user_id and a.owner_user_id == request.user.id):
        s = request.POST.get("status")
        if s in {k for k, _l in MeetingAction.STATUS}:
            a.status = s
            a.done_on = timezone.localdate() if s == "done" else None
            if "remark" in request.POST:
                a.remark = request.POST.get("remark", "").strip()[:300]
            a.save()
    else:
        messages.error(request, "Only the responsible person or the person conducting the meeting can change this.")
    return redirect(_safe_next(request, default))


# ---- minutes of meeting as a PDF (the layout of the Dehlsen MoM) ----
def _pdf_name(m):
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in m.title).strip().replace(" ", "_")[:60] or "meeting"
    return "MoM_%s_%s.pdf" % (safe, m.date.strftime("%d-%m-%Y"))


def build_mom_pdf(m):
    import io
    from weasyprint import HTML          # imported here so a WeasyPrint problem only affects PDF creation
    actions = list(m.actions.select_related("owner_user"))
    points = list(m.points.all())
    for a in actions:
        a.target_text = a.target_date.strftime("%d-%m-%y") if a.target_date else "-"
        a.owner_text = a.owner_label or "-"
        a.status_text = ("Overdue" if a.overdue else a.get_status_display()) + ((" " + a.done_on.strftime("%d-%m-%y")) if a.done_on else "")
        a.css = "late" if a.overdue else a.status
    for p in points:
        p.rows = [a for a in actions if a.point_id == p.id]
        p.lines = [ln.strip() for ln in p.notes.splitlines() if ln.strip()]
    html = render_to_string("portal/mom_pdf.html", {
        "m": m, "points": points, "loose": [a for a in actions if a.point_id is None],
        "attendees": [dict(n=i, label=t.label, present=t.present) for i, t in enumerate(m.attendees.select_related("user"), 1)],
        "s": _stats(actions), "day": m.date.strftime("%A, %d %B %Y"), "clock": m.time.strftime("%I:%M %p").lstrip("0") if m.time else "",
        "prepared": m.prepared_by or (_name(m.conducted_by) if m.conducted_by_id else ""), "approved": m.approved_by})
    return io.BytesIO(HTML(string=html).write_pdf())


def meeting_pdf(request, pk, filename=None):
    m = get_object_or_404(Meeting, pk=pk)
    resp = FileResponse(build_mom_pdf(m), as_attachment=False, filename=_pdf_name(m), content_type="application/pdf")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


def meeting_pdf_view(request, pk, filename):
    """The PDF inside our own page (Back and Share / Save), because a phone's Safari cannot open a bare PDF address."""
    m = get_object_or_404(Meeting, pk=pk)
    return render(request, "quotations/pdf_view.html", {"pdf_url": reverse("meeting_pdf_named", args=[pk, _pdf_name(m)]), "pdf_name": _pdf_name(m)})
