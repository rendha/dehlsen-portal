import datetime
import json
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_not_required
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import dashboard, notify, sales
from .models import Lead, LeadEvent, SiteDetails, SitePhoto, PushSubscription, Task, TaskType

CACHE_VERSION = "2"            # change when the icons or the offline page change, so phones fetch the new ones


def _periods(periods, director=False):
    """The quarter / year cards: only for the sales people (their place or their own target) and the directors, nobody else."""
    if director or any(p["mine"] for p in periods):
        return periods
    return []


def _is_director(user):
    profile = getattr(user, "portal_profile", None)
    return bool(user.is_superuser or (profile and profile.director))


LEAD_HEADS = {"hudha", "fousan", "imran", "rijul"}      # these four see everybody's leads


def _is_lead_head(user):
    names = {(user.get_username() or "").lower(), (user.first_name or "").lower()}
    return bool(user.is_superuser or names & LEAD_HEADS)


def _person(user):
    return user.get_full_name() or user.get_username()


def leads(request):
    """Leads.  Heads see a table per person (Hot / Medium / Cold counts) and can click a count to see those leads;
    everybody else sees the leads he entered or was given."""
    head = _is_lead_head(request.user)
    by = "assigned" if request.GET.get("by") == "assigned" else "entered"
    field = "assigned_to_id" if by == "assigned" else "entered_by_id"
    base = Lead.objects.select_related("entered_by", "assigned_to", "assigned_to2", "site").prefetch_related("events__by")
    who = request.GET.get("who", "")
    prio = request.GET.get("p", "")
    if prio not in ("hot", "medium", "cold"):
        prio = ""
    show_done = request.GET.get("done") == "1"
    summary = []
    if head:
        open_leads = list(base.filter(done=False))
        table = {}
        for l in open_leads:
            owners = [l.assigned_to, l.assigned_to2] if by == "assigned" else [l.entered_by]
            for user in owners:
                if user is None:
                    continue
                row = table.setdefault(user.id, {"id": user.id, "name": _person(user), "hot": 0, "medium": 0, "cold": 0, "total": 0})
                row[l.priority] += 1
                row["total"] += 1
        summary = sorted(table.values(), key=lambda r: (-r["hot"], -r["total"], r["name"].lower()))
        totals = {k: sum(r[k] for r in summary) for k in ("hot", "medium", "cold", "total")}
        qs = base.all()
        if who.isdigit():
            qs = qs.filter(Q(assigned_to_id=int(who)) | Q(assigned_to2_id=int(who))) if by == "assigned" else qs.filter(entered_by_id=int(who))
    else:
        totals = None
        qs = base.filter(Q(entered_by=request.user) | Q(assigned_to=request.user) | Q(assigned_to2=request.user))
    if prio:
        qs = qs.filter(priority=prio)
    if request.GET.get("stale") == "1":
        qs = qs.filter(done=False, created_at__lt=timezone.now() - datetime.timedelta(days=7))
    if not show_done:
        qs = qs.filter(done=False)
    order = {"hot": 0, "medium": 1, "cold": 2}
    items = _attach_track(_attach_stages(sorted(qs, key=lambda l: (l.done, order[l.priority], -l.created_at.timestamp()))))
    who_name = ""
    if who.isdigit() and head:
        u = User.objects.filter(pk=int(who)).first()
        who_name = _person(u) if u else ""
    attention = []
    if head:
        week_ago = timezone.now() - datetime.timedelta(days=7)
        open_all = Lead.objects.filter(done=False)
        stale = open_all.filter(created_at__lt=week_ago).count()
        hot = open_all.filter(priority="hot").count()
        overdue = sum(1 for t in Task.objects.filter(done=False) if t.overdue)
        attention = [
            {"n": stale, "title": "Leads with no follow-up for 7 days", "sub": "Leads · call these customers again", "url": reverse("leads") + "?by=%s&stale=1" % by},
            {"n": hot, "title": "Hot leads still open", "sub": "Leads · the most likely sales", "url": reverse("leads") + "?by=%s&p=hot" % by},
            {"n": overdue, "title": "Tasks past their due date", "sub": "Task · not finished yet", "url": reverse("task")},
        ]
    return render(request, "portal/leads.html", {
        "attention": attention, "head": head, "summary": summary, "totals": totals, "items": items, "by": by, "who": who, "who_name": who_name,
        "prio": prio, "show_done": show_done,
        "people_options": [{"id": u.id, "name": _person(u)} for u in User.objects.filter(is_active=True).order_by("first_name", "username")],
    })


def _attach_track(items):
    """The picture of what happened: one round tick per step in order (New, Called, Re-called, Site visit, Quoted, Won ...) and a grey
    mark for the step that is still waiting.  Also tells the card whether a call / visit was already done."""
    for l in items:
        steps = [{"label": "New", "date": timezone.localtime(l.created_at), "by": _person(l.entered_by).split(" ")[0], "state": "done", "action": "", "url": ""}]
        seen = {"call": 0, "visit": 0, "quoted": 0}
        for e in l.events.all():
            label = state = None
            action = url = ""
            if e.kind == "call":
                seen["call"] += 1
                label, action = ("Called" if seen["call"] == 1 else "Re-called"), "call"
            elif e.kind == "visit":
                seen["visit"] += 1
                label, url = ("Site visit" if seen["visit"] == 1 else "Visit again"), reverse("lead_site", args=[l.pk])
            elif e.kind == "site":
                label, url = "Site details", reverse("lead_site", args=[l.pk])
            elif e.kind == "other":
                label = "Work done"
            elif e.kind == "quoted":
                seen["quoted"] += 1
                label = "Quoted" if seen["quoted"] == 1 else "Re-quoted"
                url = "/sales/quotation/%s/" % l.quote["id"] if getattr(l, "quote", None) else ""
                action = "quote" if url else ""
            elif e.kind == "passed":
                label = "Handed over"
            elif e.kind == "won":
                label, state = "Won", "done"
            elif e.kind == "lost":
                label, state = "Lost", "lost"
            if label:
                steps.append({"label": label, "date": timezone.localtime(e.created_at), "by": (_person(e.by).split(" ")[0] if e.by else ""), "state": state or "done",
                              "action": action, "url": url})
        quote = getattr(l, "quote", None)
        if quote and seen["quoted"] == 0:
            # the quotation exists but no history line says so (a lead from before the history, or a quotation linked by phone number)
            step = {"label": "Quoted", "date": quote["date"], "by": "", "state": "done", "action": "quote", "url": "/sales/quotation/%s/" % quote["id"]}
            at = len(steps)
            for n, s in enumerate(steps[1:], 1):
                if s["date"] is not None and s["date"].date() > quote["date"]:
                    at = n
                    break
            steps.insert(at, step)
        if l.next_step and not l.lost:
            nxt = l.next_step
            steps.append({"label": nxt, "date": None, "by": "", "state": "pending",
                          "action": "call" if nxt == "Call" else "visit" if nxt == "Site visit" else "",
                          "url": "/sales/new/?lead=%s" % l.pk if nxt == "Quotation" else ""})
        l.track = steps
        l.has_call, l.has_visit = seen["call"] > 0, seen["visit"] > 0
    return items


def _digits(phone):
    d = "".join(c for c in (phone or "") if c.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def _attach_stages(items):
    """Gives every lead its stage: Lead -> Quoted (-> Waiting after 7 days) -> Confirmed, or Lost.  Quotations are matched by the saved link,
    else by the phone number; when there are several the newest is shown and any confirmed one makes the lead Confirmed."""
    try:
        from quotations.models import Quotation
        rows = list(Quotation.objects.values("id", "phone", "date", "is_customer", "offer_no"))
    except Exception:
        rows = []
    by_phone, by_id = {}, {}
    for r in rows:
        by_id[r["id"]] = r
        key = _digits(r["phone"])
        if key:
            by_phone.setdefault(key, []).append(r)
    today = timezone.localdate()
    for l in items:
        found = list(by_phone.get(_digits(l.phone), []))
        if l.quotation_id in by_id and by_id[l.quotation_id] not in found:
            found.append(by_id[l.quotation_id])
        found = [r for r in found if r["date"] >= timezone.localtime(l.created_at).date() - datetime.timedelta(days=1)] if l.quotation_id is None else found
        latest = max(found, key=lambda r: (r["date"], r["id"])) if found else None
        l.quote = latest
        if l.lost:
            l.stage, l.stage_label = "lost", "Lost" + (" · %s" % l.lost_reason if l.lost_reason else "")
        elif latest and any(r["is_customer"] for r in found):
            l.stage, l.stage_label = "confirmed", "Won"
        elif latest and (today - latest["date"]).days >= 7:
            l.stage, l.stage_label = "waiting", "Quoted · waiting %d days" % (today - latest["date"]).days
        elif latest:
            l.stage, l.stage_label = "quoted", "Quoted"
        else:
            l.stage, l.stage_label = "lead", "Lead"
    return items


def _lead_log(lead, actor, kind, text, alert=True):
    """Adds a line to the lead's history and tells the person who entered the lead (unless he did it himself)."""
    LeadEvent.objects.create(lead=lead, by=actor, kind=kind, text=text[:400])
    if alert and lead.entered_by_id and lead.entered_by_id != getattr(actor, "id", None):
        try:
            notify.send_push(lead.entered_by, "Lead: %s" % lead.customer_name, "%s %s" % (_person(actor), text), reverse("leads"))
        except Exception:
            pass


def _auto_next(lead):
    """The next step worked out from what the lead asked for and what is already in its history (so nobody has to type it)."""
    if lead.quotation_id or lead.lost:
        return ""
    wanted = [k for k in (lead.need or "").replace("both", "call,visit").split(",") if k in ("call", "visit")]
    done = {e.kind for e in lead.events.all()}
    for k in wanted:
        if k not in done:
            return "Call" if k == "call" else "Site visit"
    return "Quotation"


@require_POST
def lead_quick(request, pk):
    """One tap: 'I called' / 'I did the site visit'.  The history line and the next step are written automatically."""
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return redirect("leads")
    what = request.POST.get("what")
    if what in ("call", "visit"):
        again = any(e.kind == what for e in obj.events.all())
        _lead_log(obj, request.user, what, ("called again" if again else "called") if what == "call" else ("did the site visit again" if again else "did the site visit"))
        obj = Lead.objects.prefetch_related("events").get(pk=obj.pk)
        nxt = _auto_next(obj)
        if nxt != obj.next_step:
            obj.next_step = nxt
            obj.save(update_fields=["next_step"])
        messages.success(request, "%s - saved. Next: %s." % (obj.customer_name, nxt or "nothing"))
        if what == "visit":
            messages.info(request, "Now fill in the site details: roof size, photos and the positions.")
            return redirect(reverse("lead_site", args=[obj.pk]))
    return redirect(request.POST.get("next_url") if (request.POST.get("next_url") or "").startswith("/leads/") else "leads")


def _may_touch(user, lead):
    return _is_lead_head(user) or user.id in (lead.entered_by_id, lead.assigned_to_id, lead.assigned_to2_id)


@require_POST
def lead_update(request, pk):
    """The person following up says what happened, what comes next, and (if needed) who does it next."""
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return redirect("leads")
    what = request.POST.get("what", "")
    note = request.POST.get("note", "").strip()[:300]
    nxt = request.POST.get("next", "")
    nxt_text = {"call": "Call", "visit": "Site visit", "quotation": "Quotation", "later": "Decide later"}.get(nxt) or (request.POST.get("next_other", "").strip()[:100] if nxt == "other" else "")
    person = User.objects.filter(pk=request.POST.get("person"), is_active=True).first() if (request.POST.get("person") or "").isdigit() else None
    label = {"call": "called", "visit": "did the site visit", "other": "did some work"}.get(what)
    if label:
        _lead_log(obj, request.user, what, label + (": " + note if note else ""))
    elif note:
        _lead_log(obj, request.user, "note", "noted: " + note)
    changed = []
    if nxt_text and nxt_text != obj.next_step:
        obj.next_step = "" if nxt == "later" else nxt_text
        changed.append("next_step")
        _lead_log(obj, request.user, "next", "set the next step: " + nxt_text, alert=False)
    if person and person.id != obj.assigned_to_id:
        old = obj.assigned_to
        obj.assigned_to = person
        changed.append("assigned_to")
        _lead_log(obj, request.user, "passed", "handed the lead from %s to %s" % (_person(old) if old else "nobody", _person(person)))
        if person.id != request.user.id:
            try:
                notify.send_push(person, "Lead for you: %s" % obj.customer_name, "%s - next: %s" % (_person(request.user), obj.next_step or "see the lead"), reverse("leads"))
            except Exception:
                pass
    if changed:
        obj.save(update_fields=changed)
    messages.success(request, "Updated: %s." % obj.customer_name)
    return redirect(request.POST.get("next_url") if (request.POST.get("next_url") or "").startswith("/leads/") else "leads")


def _site_ready(lead):
    """The site details count as done when the roof size or at least one photo is there."""
    site = SiteDetails.objects.filter(lead=lead).first()
    return bool(site and (site.roof_length or site.roof_width) or SitePhoto.objects.filter(lead=lead).exists())


def _make_won(request, obj):
    _attach_stages([obj])
    if not obj.quote:
        messages.error(request, "This lead has no quotation yet.")
        return
    from quotations import dashboard_stats as stats
    from quotations.models import Quotation
    quotation = Quotation.objects.get(pk=obj.quote["id"])
    if not quotation.is_customer:
        key = stats.client_key(stats.rows_of([quotation])[0])
        same = [q.id for q in Quotation.objects.all() if stats.client_key(stats.rows_of([q])[0]) == key]
        Quotation.objects.filter(id__in=same).update(counted=False, is_customer=False)     # one confirmed quotation per client
        Quotation.objects.filter(id=quotation.id).update(counted=True, is_customer=True)
    if obj.quotation_id != quotation.id:
        obj.quotation_id = quotation.id
        obj.save(update_fields=["quotation_id"])
    _lead_log(obj, request.user, "won", "marked the lead WON - the customer said yes")
    messages.success(request, "Won! %s is now a customer - the project person can prepare the material list." % obj.customer_name)


@require_POST
def lead_won(request, pk):
    """The customer said yes: the lead's newest quotation becomes a customer.  The site details must be filled in first."""
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return redirect("leads")
    if not _site_ready(obj):
        messages.warning(request, "Fill in the site details first (roof size or photos). Saving them will mark the lead Won.")
        return redirect(reverse("lead_site", args=[obj.pk]) + "?then=won")
    _make_won(request, obj)
    return redirect(request.POST.get("next") if (request.POST.get("next") or "").startswith("/leads/") else "leads")


SITE_TEXT = [
    ("roof_length", "Roof length", "e.g. 40 ft", "line"), ("roof_width", "Roof width", "e.g. 25 ft", "line"),
    ("roof_layout", "Roof / plant layout", "Where the panels go, shadow areas, roof type, tilt ...", "area"),
    ("inverter_position", "Inverter position", "Where the inverter will be fixed", "line"),
    ("acdb_position", "ACDB position", "", "line"), ("dcdb_position", "DCDB position", "", "line"),
    ("earth_rod_position", "Earth rod position", "", "line"),
    ("cable_laying", "Cable laying", "Route of the DC and AC cables, conduit, length", "area"),
    ("meter_position", "Meter position", "Where the net meter / energy meter is", "line"),
]


def lead_site(request, pk):
    """The site details of a lead: roof size, layout, positions, cable route and photos."""
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return redirect("leads")
    site = SiteDetails.objects.filter(lead=obj).first()
    then = request.GET.get("then") or request.POST.get("then") or ""
    if request.method == "POST":
        values = {k: request.POST.get(k, "").strip()[:2000] for k, *_ in SITE_TEXT}
        site, _ = SiteDetails.objects.update_or_create(lead=obj, defaults=dict(values, updated_by=request.user, updated_at=timezone.now()))
        for pid in request.POST.getlist("delete"):
            if pid.isdigit():
                SitePhoto.objects.filter(lead=obj, pk=int(pid)).delete()
        added = 0
        for f in request.FILES.getlist("photos"):
            if f.size <= 6 * 1024 * 1024 and (f.content_type or "").startswith("image/"):
                SitePhoto.objects.create(lead=obj, data=f.read(), content_type=f.content_type, caption=f.name[:120])
                added += 1
        _lead_log(obj, request.user, "site", "saved the site details" + (" (%d photo%s added)" % (added, "" if added == 1 else "s") if added else ""))
        if then == "won":
            if _site_ready(obj):
                _make_won(request, obj)
            else:
                messages.warning(request, "Add the roof size or a photo, then the lead can be marked Won.")
                return redirect(reverse("lead_site", args=[obj.pk]) + "?then=won")
        else:
            messages.success(request, "Site details saved for %s." % obj.customer_name)
        return redirect("leads")
    fields = [{"name": k, "label": label, "hint": hint, "kind": kind, "value": getattr(site, k, "") if site else ""} for k, label, hint, kind in SITE_TEXT]
    photos = list(SitePhoto.objects.filter(lead=obj).values_list("id", flat=True))
    return render(request, "portal/lead_site.html", {"lead": obj, "fields": fields, "photos": photos, "then": then})


def lead_photo(request, pk, photo_id):
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return HttpResponse(status=403)
    photo = get_object_or_404(SitePhoto, pk=photo_id, lead=obj)
    return HttpResponse(bytes(photo.data), content_type=photo.content_type or "image/jpeg")


@require_POST
def lead_lost(request, pk):
    obj = get_object_or_404(Lead, pk=pk)
    if not (_is_lead_head(request.user) or request.user.id in (obj.entered_by_id, obj.assigned_to_id, obj.assigned_to2_id)):
        return redirect("leads")
    reason = request.POST.get("reason", "").strip()[:100]
    if request.POST.get("undo"):
        obj.lost, obj.lost_reason, obj.done = False, "", False
    else:
        obj.lost, obj.lost_reason, obj.done = True, reason, True
    obj.save(update_fields=["lost", "lost_reason", "done"])
    _lead_log(obj, request.user, "lost" if not request.POST.get("undo") else "note",
              ("marked the lead LOST" + (" - " + reason if reason else "")) if not request.POST.get("undo") else "reopened the lead")
    return redirect(request.POST.get("next") if (request.POST.get("next") or "").startswith("/leads/") else "leads")


def _read_type(src):
    """customer type, DCR choice, system type (+ typed text) from a posted form; wrong values become blank."""
    ct = src.get("customer_type", "")
    ct = ct if ct in ("residential", "commercial", "industrial") else ""
    dcr = src.get("dcr_choice", "") if ct == "residential" else ""
    dcr = dcr if dcr in ("dcr", "non_dcr", "undecided") else ("undecided" if ct == "residential" else "")
    st = src.get("system_type", "")
    st = st if st in ("on_grid", "off_grid", "hybrid", "other") else ""
    other = (src.get("system_other", "") or "").strip()[:100] if st == "other" else ""
    return ct, dcr, st, other


def _type_text(ct, dcr, st, other):
    names = {"residential": "Residential", "commercial": "Commercial", "industrial": "Industrial", "dcr": "DCR", "non_dcr": "Non-DCR",
             "undecided": "DCR/Non-DCR not decided", "on_grid": "On-grid", "off_grid": "Off-grid", "hybrid": "Hybrid"}
    parts = [names[ct]] if ct else []
    if dcr:
        parts.append(names[dcr])
    if st:
        parts.append(other or "Other" if st == "other" else names[st])
    return ", ".join(parts) or "not set"


@require_POST
def lead_type(request, pk):
    """Change the customer type / DCR / system type after the lead is saved (e.g. on-grid first, hybrid later); it goes in the history."""
    obj = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, obj):
        return redirect("leads")
    old = _type_text(obj.customer_type, obj.dcr_choice, obj.system_type, obj.system_other)
    obj.customer_type, obj.dcr_choice, obj.system_type, obj.system_other = _read_type(request.POST)
    new = _type_text(obj.customer_type, obj.dcr_choice, obj.system_type, obj.system_other)
    if new != old:
        obj.save(update_fields=["customer_type", "dcr_choice", "system_type", "system_other"])
        _lead_log(obj, request.user, "type", "changed the type from %s to %s" % (old, new), alert=False)
        messages.success(request, "Updated the type of %s: %s." % (obj.customer_name, new))
    return redirect(request.POST.get("next_url") if (request.POST.get("next_url") or "").startswith("/leads/") else "leads")


def lead_new(request):
    people = [u for u in User.objects.filter(is_active=True).order_by("first_name", "username")]
    error = ""
    values = {"customer_name": "", "phone": "", "area": "", "need_choice": "call", "other_text": "", "priority": "medium", "note": "", "assigned_to": "", "assigned_to2": "",
              "customer_type": "", "dcr_choice": "", "system_type": "", "system_other": ""}
    if request.method == "POST":
        values = {k: request.POST.get(k, "").strip() for k in values}
        person = User.objects.filter(pk=values["assigned_to"], is_active=True).first() if values["assigned_to"].isdigit() else None
        person2 = User.objects.filter(pk=values["assigned_to2"], is_active=True).first() if values["assigned_to2"].isdigit() else None
        need = values["need_choice"] if values["need_choice"] in ("call", "visit", "call,visit", "other") else ""
        if need == "other" and not values["other_text"]:
            need = ""
            error = "Type what has to be done."
        if error:
            pass
        elif not values["customer_name"]:
            error = "Type the customer's name."
        elif values["priority"] not in ("hot", "medium", "cold"):
            error = "Choose Cold, Medium or Hot."
        elif not need:
            error = "Choose what should be done."
        elif not person:
            error = "Choose who gets this lead."
        elif person2 and person2.id == person.id:
            error = "The two people must be different."
        if not error:
            ctype, dcr, stype, sother = _read_type(values)
            lead = Lead.objects.create(customer_type=ctype, dcr_choice=dcr, system_type=stype, system_other=sother, customer_name=values["customer_name"], phone=values["phone"], area=values["area"],
                                       need=need, need_other=values["other_text"] if need == "other" else "", priority=values["priority"], note=values["note"],
                                       entered_by=request.user, assigned_to=person, assigned_to2=person2)
            lead.next_step = _auto_next(lead)
            lead.save(update_fields=["next_step"])
            for target in (person, person2):
              if target and target.id != request.user.id:
                try:
                    notify.send_push(target, "New %s lead from %s" % (lead.get_priority_display(), _person(request.user)),
                                     "%s - %s" % (lead.customer_name, ", ".join(lead.need_list)), reverse("leads"))
                except Exception:
                    pass
            return redirect("leads")
    return render(request, "portal/lead_new.html", {
        "people": [{"id": u.id, "name": _person(u)} for u in people], "values": values, "error": error})


@require_POST
def lead_done(request, pk):
    obj = get_object_or_404(Lead, pk=pk)
    if not (_is_lead_head(request.user) or request.user.id in (obj.entered_by_id, obj.assigned_to_id, obj.assigned_to2_id)):
        return redirect("leads")
    obj.done = not obj.done
    obj.save(update_fields=["done"])
    messages.success(request, "%s marked done. It is hidden from the open list - tap \"Include done\" to see it again." % obj.customer_name if obj.done
                     else "%s is open again." % obj.customer_name)
    return redirect(request.POST.get("next") if (request.POST.get("next") or "").startswith("/leads/") else "leads")


def home(request):
    """The four buttons.  Everybody who signed in sees all four."""
    show_dash = _is_director(request.user) or _is_lead_head(request.user)
    rng = request.GET.get("r") if request.GET.get("r") in ("month", "quarter", "year") else "month"
    return render(request, "portal/home.html", {"name": request.user.get_full_name() or request.user.get_username(),
                                                "dash": dashboard.build(rng) if show_dash else None, "rng": rng,
                                                "periods": _periods(sales.for_user(request.user), director=_is_director(request.user))})


def targets(request):
    """Everybody's target, achieved and percent: for the sales people and the directors only."""
    periods = _periods(sales.for_user(request.user), director=_is_director(request.user))
    if not periods:
        return redirect("home")
    return render(request, "portal/targets.html", {"periods": periods})


User = get_user_model()
BLUE, GREEN, ORANGE, RED, GREY = "#3B73B9", "#2e9e5b", "#E8730C", "#d64545", "#9aa5b4"


def _safe_next(request, default):
    target = request.POST.get("next") or request.GET.get("next") or ""
    return target if target.startswith("/task/") else default


def _task_row(task, user):
    """One task as the pages and the calendar show it."""
    return {
        "id": task.id, "type": task.task_type.name, "details": task.details,
        "by": notify.name_of(task.created_by), "to": notify.name_of(task.assigned_to),
        "added": "%d %s" % (timezone.localtime(task.created_at).day, timezone.localtime(task.created_at).strftime("%b")),
        "due": task.due_text(), "left": task.left_text(), "done": task.done, "overdue": task.overdue,
        "mine": task.assigned_to_id == user.id, "url": reverse("task_detail", args=[task.id]),
    }


def task(request):
    """The Task page: the calendar (schedules + tasks), who gave what, and the button to give a task."""
    tasks = list(Task.objects.select_related("task_type", "created_by", "assigned_to").filter(done=False))
    recent_done = list(Task.objects.select_related("task_type", "created_by", "assigned_to").filter(done=True).order_by("-done_at")[:10])
    rows = [_task_row(t, request.user) for t in tasks + recent_done]
    people = sorted({r["to"] for r in rows})
    directory = [{"name": t.name, "people": [{"name": a.user.get_full_name() or a.user.get_username(), "note": a.note}
                                             for a in t.assignments.all() if a.user.is_active]}
                 for t in TaskType.objects.prefetch_related("assignments__user")]
    return render(request, "portal/task.html", {
        "rows": rows, "people": people, "directory": directory,
        "pending_mine": sum(1 for t in tasks if t.assigned_to_id == request.user.id),
    })


def task_events(request):
    """JSON for the calendar: the cleaning / service schedule AND the tasks, between ?start and ?end."""
    def day(value, default):
        try:
            return datetime.date.fromisoformat((value or "")[:10])
        except ValueError:
            return default
    today = timezone.localdate()
    start = day(request.GET.get("start"), today - datetime.timedelta(days=40))
    end = day(request.GET.get("end"), today + datetime.timedelta(days=80))
    events = []

    for t in Task.objects.select_related("task_type", "created_by", "assigned_to").filter(due_date__gte=start, due_date__lt=end):
        row = _task_row(t, request.user)
        color = GREY if t.done else RED if t.overdue else ORANGE
        events.append({
            "id": "t%d" % t.id, "title": "%s · %s→%s" % (t.task_type.name, row["by"].split(" ")[0], row["to"].split(" ")[0]),
            "start": t.due_date.isoformat() + ("T" + t.due_time.strftime("%H:%M:%S") if t.due_time else ""),
            "allDay": t.due_time is None, "backgroundColor": color, "borderColor": color,
            "extendedProps": dict(row, kind="task", person=row["to"]),
        })

    try:
        from cleaning.models import CleaningSchedule
        schedules = (CleaningSchedule.objects.select_related("customer", "site", "assigned_to", "service_type")
                     .filter(scheduled_date__gte=start, scheduled_date__lt=end).exclude(status="Cancelled"))
        for s in schedules:
            service = s.service_name
            cleaning = service.strip().lower() == "cleaning"
            name = s.get_customer_name() or ""
            color = GREY if s.status == "Completed" else (BLUE if cleaning else GREEN)
            events.append({
                "id": "s%d" % s.id, "title": name if cleaning else "%s – %s" % (service, name),
                "start": s.scheduled_date.isoformat() + ("T" + s.scheduled_time.strftime("%H:%M:%S") if s.scheduled_time else ""),
                "allDay": s.scheduled_time is None, "backgroundColor": color, "borderColor": color,
                "extendedProps": {
                    "kind": "cleaning" if cleaning else "service", "type": service, "customer": name,
                    "place": s.get_location() or "", "status": s.status, "notes": s.notes or "",
                    "person": notify.name_of(s.assigned_to) if s.assigned_to_id else "",
                },
            })
    except Exception:                       # the calendar still shows the tasks if the Service tables are not ready
        pass
    return JsonResponse(events, safe=False)


def task_new(request):
    """Give a task: pick the task, then only the people who do that task are shown."""
    types = list(TaskType.objects.prefetch_related("assignments__user"))
    crew = {str(t.id): [{"id": a.user_id, "name": a.user.get_full_name() or a.user.get_username(), "note": a.note}
                        for a in t.assignments.all() if a.user.is_active] for t in types}
    error = ""
    values = {"type": request.GET.get("type", ""), "person": "", "details": "", "due_date": request.GET.get("date", ""), "due_time": ""}
    if request.method == "POST":
        values = {k: request.POST.get(k, "").strip() for k in values}
        task_type = TaskType.objects.filter(pk=values["type"] or 0).first() if values["type"].isdigit() else None
        person = task_type.people.filter(pk=values["person"], is_active=True).first() if task_type and values["person"].isdigit() else None
        try:
            due_date = datetime.date.fromisoformat(values["due_date"])
        except ValueError:
            due_date = None
        due_time = None
        if values["due_time"]:
            try:
                due_time = datetime.time.fromisoformat(values["due_time"])
            except ValueError:
                error = "The time is not valid."
        if not task_type:
            error = "Choose the task."
        elif not person:
            error = "Choose a person who does this task."
        elif not due_date:
            error = "Choose the due date."
        if not error:
            created = Task.objects.create(task_type=task_type, details=values["details"], created_by=request.user,
                                          assigned_to=person, due_date=due_date, due_time=due_time)
            notify.send_push(person, "New task from %s" % notify.name_of(request.user),
                             "%s – due %s" % (task_type.name, created.due_text()), reverse("task_mine"))
            return redirect(reverse("task_detail", args=[created.id]) + "?new=1")
    return render(request, "portal/task_new.html", {"types": types, "crew": crew, "values": values, "error": error})


def task_detail(request, pk):
    obj = get_object_or_404(Task.objects.select_related("task_type", "created_by", "assigned_to"), pk=pk)
    link = request.build_absolute_uri(reverse("task_mine"))
    can_finish = request.user.is_superuser or request.user.id in (obj.assigned_to_id, obj.created_by_id)
    return render(request, "portal/task_detail.html", {
        "t": obj, "row": _task_row(obj, request.user), "new": request.GET.get("new") == "1", "can_finish": can_finish,
        "wa_link": notify.whatsapp_link(obj, link), "has_number": bool(notify.whatsapp_number(obj.assigned_to)),
        "message": notify.message_text(obj, link),
    })


def task_mine(request):
    """My tasks (sorted by due date) and the tasks I gave."""
    base = Task.objects.select_related("task_type", "created_by", "assigned_to")
    mine = [_task_row(t, request.user) for t in base.filter(assigned_to=request.user, done=False)]
    finished = [_task_row(t, request.user) for t in base.filter(assigned_to=request.user, done=True).order_by("-done_at")[:10]]
    given = [_task_row(t, request.user) for t in base.filter(created_by=request.user).order_by("done", "due_date")[:40]]
    return render(request, "portal/task_mine.html", {
        "mine": mine, "finished": finished, "given": given,
        "push_on": notify.push_enabled(), "vapid_key": os.environ.get("VAPID_PUBLIC_KEY", ""),
        "has_phone": PushSubscription.objects.filter(user=request.user).exists(),
    })


@require_POST
def task_done(request, pk):
    obj = get_object_or_404(Task, pk=pk)
    if not (request.user.is_superuser or request.user.id in (obj.assigned_to_id, obj.created_by_id)):
        return redirect("task_mine")
    if request.POST.get("undo"):
        obj.done, obj.done_at = False, None
    else:
        obj.done, obj.done_at = True, timezone.now()
        if obj.created_by_id and obj.created_by_id != request.user.id:
            notify.send_push(obj.created_by, "Task done", "%s finished: %s" % (notify.name_of(request.user), obj.task_type.name), reverse("task"))
    obj.save(update_fields=["done", "done_at"])
    return redirect(_safe_next(request, reverse("task_mine")))


@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        endpoint, keys = data["endpoint"], data["keys"]
        PushSubscription.objects.update_or_create(endpoint=endpoint[:500], defaults={
            "user": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"]})
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True})


@require_POST
def push_test(request):
    sent = notify.send_push(request.user, "Dehlsen test alert", "Phone alerts are working.", reverse("task_mine"))
    return JsonResponse({"sent": sent})


@login_not_required
def manifest(request):
    return JsonResponse({
        "id": "/",
        "name": "Dehlsen Energy",
        "short_name": "Dehlsen",
        "description": "Sales, Project, Service and Task",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": "#3B73B9",
        "background_color": "#f4f7fb",
        "lang": "en-IN",
        "icons": [
            {"src": static("portal/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": static("portal/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }, content_type="application/manifest+json")


@login_not_required
def service_worker(request):
    """Keeps only the icons and the offline page.  Pages with quotations, stock or customers are NEVER stored on the phone."""
    files = [static("portal/icon-192.png"), static("portal/icon-512.png"), "/offline/"]
    script = """
const CACHE = "dehlsen-%(version)s";
const FILES = %(files)s;
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((n) => Promise.all(n.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET") { return; }
  const u = new URL(r.url);
  if (u.origin !== self.location.origin) { return; }
  if (r.mode === "navigate") { e.respondWith(fetch(r).catch(() => caches.match("/offline/"))); return; }
  if (u.pathname.startsWith("/static/")) { e.respondWith(caches.match(r).then((hit) => hit || fetch(r))); }
});
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data.json(); } catch (err) { d = { title: "Dehlsen", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Dehlsen", {
    body: d.body || "", icon: "/static/portal/icon-192.png", badge: "/static/portal/icon-192.png", data: { url: d.url || "/task/mine/" } }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/task/mine/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});
""" % {"version": CACHE_VERSION, "files": json.dumps(files)}
    response = HttpResponse(script, content_type="text/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_not_required
def offline(request):
    return render(request, "portal/offline.html")
