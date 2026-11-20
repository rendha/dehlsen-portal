"""The customer's own page: when the material comes, when each piece of work is planned, and what is already done.
The customer opens a private link (no login); the project team sets the dates and sends the link with a click-to-chat WhatsApp message.
No money, margins or internal notes are ever shown on it.  English and Malayalam."""
import datetime
import re
import secrets
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import project_work
from .models import ProjectWork

DOC_TEAM_NAME = "Anupama"                 # documentation team contact in the welcome message
CONTACT_PHONE = "+91 97784 24535"          # shown on the customer page: change it here

STEPS = [("site_visit", "Site visit"), ("feasibility", "Feasibility approval"), ("material", "Material delivery"), ("structure", "Structure work"),
         ("panel", "Panel mounting"), ("electrical", "Electrical work"), ("inverter", "Inverter installation"),
         ("inspection", "KSEB inspection"), ("commissioning", "Commissioning"), ("handover", "Document handover")]

STEP_ML = {"site_visit": "സൈറ്റ് സന്ദർശനം", "feasibility": "ഫീസിബിലിറ്റി അംഗീകാരം", "material": "സാധനങ്ങൾ എത്തിക്കൽ", "structure": "സ്ട്രക്ചർ പണി",
           "panel": "പാനൽ സ്ഥാപിക്കൽ", "electrical": "ഇലക്ട്രിക്കൽ പണി", "inverter": "ഇൻവെർട്ടർ സ്ഥാപിക്കൽ", "inspection": "കെഎസ്ഇബി പരിശോധന",
           "commissioning": "കമ്മീഷനിംഗ്", "handover": "രേഖകൾ കൈമാറൽ"}

TEXT = {
    "en": {"hello": "Hello", "title": "here is your solar project", "steps_done": "steps done", "of": "of", "schedule": "Your schedule", "done": "Done", "completed": "Completed",
           "planned_for": "Planned for", "rescheduled": "being rescheduled, we will update you", "soon": "Date will be shared soon", "next": "Next step",
           "today": "today", "tomorrow": "tomorrow", "in_days": "in %d days", "overdue": "date has passed, we will update you", "all_done": "All steps are complete. Thank you!",
           "system": "Your system", "capacity": "Capacity", "panels": "Solar panels", "inverter": "Inverter", "type": "System type", "project_id": "Project ID", "place": "Place",
           "contact": "Your contact", "engineer": "Site engineer", "call": "Call", "wa": "Message us on WhatsApp", "updated": "Updated", "tagline": "Powering the future with clean energy",
           "back": "Back to project", "lang_en": "English", "lang_ml": "മലയാളം", "wa_hello": "Hello Dehlsen Energy, I am %s (project %s)."},
    "ml": {"hello": "നമസ്കാരം", "title": "നിങ്ങളുടെ സോളാർ പ്രോജക്റ്റ്", "steps_done": "ഘട്ടങ്ങൾ പൂർത്തിയായി", "of": "/", "schedule": "നിങ്ങളുടെ ഷെഡ്യൂൾ", "done": "പൂർത്തിയായി",
           "completed": "പൂർത്തിയാക്കി", "planned_for": "തീയതി", "rescheduled": "പുതിയ തീയതി ഉടൻ അറിയിക്കാം", "soon": "തീയതി ഉടൻ അറിയിക്കാം", "next": "അടുത്ത ഘട്ടം",
           "today": "ഇന്ന്", "tomorrow": "നാളെ", "in_days": "%d ദിവസത്തിനുള്ളിൽ", "overdue": "തീയതി കഴിഞ്ഞു, പുതിയ തീയതി അറിയിക്കാം",
           "all_done": "എല്ലാ ഘട്ടങ്ങളും പൂർത്തിയായി. നന്ദി!", "system": "നിങ്ങളുടെ സിസ്റ്റം", "capacity": "ശേഷി", "panels": "സോളാർ പാനലുകൾ", "inverter": "ഇൻവെർട്ടർ",
           "type": "സിസ്റ്റം തരം", "project_id": "പ്രോജക്റ്റ് ഐഡി", "place": "സ്ഥലം", "contact": "ബന്ധപ്പെടാൻ", "engineer": "സൈറ്റ് എൻജിനീയർ", "call": "വിളിക്കുക",
           "wa": "വാട്സ്ആപ്പിൽ സന്ദേശം അയയ്ക്കുക", "updated": "പുതുക്കിയത്", "tagline": "Powering the future with clean energy", "back": "പ്രോജക്റ്റിലേക്ക് തിരികെ",
           "lang_en": "English", "lang_ml": "മലയാളം", "wa_hello": "നമസ്കാരം ഡെൽസൻ എനർജി, ഞാൻ %s (പ്രോജക്റ്റ് %s)."},
}


def _lang(request):
    got = request.GET.get("lang") or request.COOKIES.get("track_lang") or "en"
    return got if got in TEXT else "en"


def _done(w, key, today):
    if key == "site_visit":
        return bool(w.site_estimation)
    if key == "feasibility":
        return w.feasibility == "ok" or bool(w.feasibility_date)
    if key == "material":
        return w.material_dispatched is True
    if key == "structure":
        return bool(w.structure)
    if key == "panel":
        return bool(w.panel_done)
    if key == "inverter":
        return bool(w.inverter_done)
    if key == "electrical":
        return bool(w.electrical)
    if key == "inspection":
        return bool(project_work.kseb_date(w, "inspection"))
    if key == "handover":
        return bool(w.handover)
    if key == "commissioning":
        return bool(w.commission_date and w.commission_date <= today)
    return False


def _date(v):
    try:
        return datetime.date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def steps_of(w, today=None, lang="en"):
    """Every step with its planned date and state: done / late / planned / later."""
    today = today or timezone.localdate()
    plan = dict(w.customer_plan or {})
    if "install" in plan and "panel" not in plan:          # dates saved before panel and inverter were separate steps
        plan["panel"] = plan["install"]
    out = []
    for key, label in STEPS:
        planned, done = _date(plan.get(key)), _done(w, key, today)
        state = "done" if done else ("late" if planned and planned < today else ("planned" if planned else "later"))
        out.append({"key": key, "label": STEP_ML[key] if lang == "ml" else label, "planned": planned, "done": done, "state": state})
    return out


def ensure_token(w):
    if not w.track_token:
        w.track_token = secrets.token_urlsafe(16)
        w.save(update_fields=["track_token"])
    return w.track_token


def _d(d):
    return d.strftime("%d %b %Y")


def _first_name(w):
    name = re.sub(r"^(mr|mrs|ms|dr|er|adv)\.?\s+", "", (w.name or "").strip(), flags=re.I)
    return (name.split() or ["there"])[0].title()


def _link(url, lang):
    return url + ("?lang=ml" if lang == "ml" else "")


def _greet_name(w):
    """Keeps the title, so a doctor stays Dr. Sujith."""
    m = re.match(r"^(mr|mrs|ms|dr|er|adv)\.?\s+(\S+)", (w.name or "").strip(), flags=re.I)
    if m:
        t = m.group(1).title()
        return "%s%s %s" % (t, "" if t.lower() == "adv" else ".", m.group(2).title())
    return _first_name(w)


def _who(name):
    return (" - %s" % re.sub(r"\s+", " ", name.strip()).title()) if (name or "").strip() else ""


def welcome_text(w, url, lang="en"):
    pid = (" " + w.project_id) if w.project_id else ""
    sales, eng, doc = _who(w.sales_person), _who(w.engineer), _who(DOC_TEAM_NAME)
    if lang == "ml":
        return "\n".join([
            "പ്രിയ %s," % _greet_name(w), "",
            "ഡെൽസൻ എനർജി കുടുംബത്തിലേക്ക് സ്വാഗതം! ☀️",
            "നിങ്ങളുടെ സോളാർ പ്രോജക്റ്റ്%s ഞങ്ങളെ ഏൽപ്പിച്ചതിന് നന്ദി." % pid, "",
            "ഇനി മുതൽ നിങ്ങളുടെ പ്രോജക്റ്റ് നിർമ്മിക്കുന്ന ടീമുകൾ ഓരോ ഘട്ടത്തിലും നിങ്ങളെ സഹായിക്കും:", "",
            "🤝 *സെയിൽസ് ടീം*%s" % sales, "ഇതുവരെ നിങ്ങളുമായി സംസാരിച്ചത് ഇവരാണ്. നിങ്ങളുടെ ആവശ്യങ്ങൾ എല്ലാം ടീമിന് കൈമാറിയിട്ടുണ്ട്.", "",
            "🛠️ *പ്രോജക്ട് ടീം*%s" % eng, "മെറ്റീരിയൽ ഡെലിവറി, സ്ട്രക്ചർ, പാനൽ, ഇലക്ട്രിക്കൽ, ഇൻവെർട്ടർ ഇൻസ്റ്റലേഷൻ എന്നിവ. സൈറ്റിൽ വരുന്നതിന് മുൻപ് വിളിക്കും.", "",
            "📄 *ഡോക്യുമെന്റേഷൻ ടീം*%s" % doc, "KSEB അപേക്ഷ, ഇൻസ്പെക്ഷൻ, നെറ്റ് മീറ്ററിംഗ്, സബ്സിഡി രേഖകൾ, അവസാന ഹാൻഡോവർ ഫയൽ.", "",
            "📍 ഓരോ ഘട്ടവും എപ്പോൾ വേണമെങ്കിലും ഇവിടെ കാണാം:", _link(url, lang),
            "തീയതികളിൽ മാറ്റമുണ്ടെങ്കിൽ ഞങ്ങൾ ആദ്യം അറിയിക്കും.", "",
            "📞 സഹായത്തിന്: %s (പ്രോജക്റ്റ് നമ്പർ പറയുക)" % CONTACT_PHONE, "",
            "ഹൃദയപൂർവ്വം,", "ടീം ഡെൽസൻ എനർജി"])
    return "\n".join([
        "Dear %s," % _greet_name(w), "",
        "Welcome to the Dehlsen Energy family! ☀️",
        "Thank you for trusting us with your solar project%s. We're delighted to have you with us." % pid, "",
        "From here, your project moves from our sales team to the people who will build it. Here is who will look after you at each stage:", "",
        "🤝 *Sales team*%s" % sales, "Your contact until now. They have handed over everything we discussed, so you won't need to repeat yourself.", "",
        "🛠️ *Project team*%s" % eng, "Handles material delivery, structure, panel mounting, electrical work and inverter installation at your site. They will call you before every site visit.", "",
        "📄 *Documentation team*%s" % doc, "Handles the KSEB application, inspection and net-metering paperwork, subsidy documents and your final handover file.", "",
        "📍 *Track every step, any time:*", _link(url, lang),
        "You will see what is done, what is next and the expected dates. We'll message you at each milestone, and if any date changes we will tell you first.", "",
        "📞 *Need anything?* Call or WhatsApp us on %s. Please quote your project number%s." % (CONTACT_PHONE, pid), "",
        "Thank you once again. We look forward to powering your home with clean energy.", "",
        "Warm regards,", "Team Dehlsen Energy"])


def schedule_text(w, steps, url, lang="en"):
    pid = (" " + w.project_id) if w.project_id else ""
    nxt = [s for s in steps if not s["done"] and s["planned"]][:2]
    if lang == "ml":
        lines = ["നമസ്കാരം %s, നിങ്ങളുടെ സോളാർ പ്രോജക്റ്റ്%s ബുക്ക് ചെയ്തിരിക്കുന്നു." % (_first_name(w), pid)]
        if nxt:
            lines.append("പ്രതീക്ഷിക്കുന്ന തീയതികൾ: " + ", ".join("%s - %s" % (s["label"], _d(s["planned"])) for s in nxt) + ".")
        return "\n".join(lines + ["എന്തെങ്കിലും മാറ്റമുണ്ടെങ്കിൽ ഞങ്ങൾ അറിയിക്കും. പുരോഗതി ഇവിടെ കാണാം:", _link(url, lang), "", "ഡെൽസൻ എനർജി"])
    lines = ["Hello %s, your solar project%s is booked." % (_first_name(w), pid)]
    if nxt:
        lines.append("Expected dates: " + ", ".join("%s around %s" % (s["label"], _d(s["planned"])) for s in nxt) + ".")
    return "\n".join(lines + ["We'll message you if anything changes. Track progress here:", _link(url, lang), "", "Dehlsen Energy"])


def update_text(w, steps, url, lang="en"):
    done = [s for s in steps if s["done"]]
    nxt = next((s for s in steps if not s["done"] and s["planned"]), None)
    pid = (" " + w.project_id) if w.project_id else ""
    if lang == "ml":
        lines = ["നമസ്കാരം %s, ഡെൽസൻ എനർജിയിൽ നിന്ന് നിങ്ങളുടെ സോളാർ പ്രോജക്റ്റ്%s സംബന്ധിച്ച അപ്ഡേറ്റ്." % (_first_name(w), pid)]
        if done:
            lines.append("പൂർത്തിയായത്: %s." % ", ".join(s["label"] for s in done))
        if nxt:
            lines.append("അടുത്തത്: %s - %s." % (nxt["label"], _d(nxt["planned"])))
        return "\n".join(lines + ["", "പൂർണ്ണ ഷെഡ്യൂൾ:", _link(url, lang)])
    lines = ["Hello %s, an update on your solar project%s from Dehlsen Energy." % (_first_name(w), pid)]
    if done:
        lines.append("Done: %s." % ", ".join(s["label"] for s in done))
    if nxt:
        lines.append("Next: %s on %s." % (nxt["label"], _d(nxt["planned"])))
    return "\n".join(lines + ["", "Full schedule:", _link(url, lang)])


def wa_link(phone, text):
    digits = re.sub(r"\D", "", phone or "").lstrip("0")
    if len(digits) == 10:
        digits = "91" + digits
    return ("https://wa.me/%s?text=%s" % (digits, quote(text))) if len(digits) >= 11 else ""


def manage(request, pk):
    """The project team: set the planned dates, copy the customer's link, send it on WhatsApp (English or Malayalam)."""
    if not project_work.can_edit(request.user):
        return HttpResponseForbidden("Only the project team sets the customer's schedule.")
    w = get_object_or_404(ProjectWork, pk=pk)
    if request.method == "POST":
        plan = dict(w.customer_plan or {})
        plan.pop("install", None)
        for key, _label in STEPS:
            raw = (request.POST.get("plan_" + key) or "").strip()
            if raw and _date(raw):
                plan[key] = raw
            else:
                plan.pop(key, None)
        w.customer_plan = plan
        w.save(update_fields=["customer_plan"])
        messages.success(request, "Dates saved.")
        return redirect("progress_customer", pk=w.pk)
    url = request.build_absolute_uri("/track/%s/" % ensure_token(w))
    steps = steps_of(w)
    has_dates = any(s["planned"] or s["done"] for s in steps)
    ml_steps = steps_of(w, lang="ml")
    ctx = {"w": w, "steps": steps, "url": url, "has_dates": has_dates, "no_phone": not wa_link(w.phone, "x"),
           "wa_welcome": wa_link(w.phone, welcome_text(w, url)),
           "wa_schedule": wa_link(w.phone, schedule_text(w, steps, url)) if has_dates else "",
           "wa_update": wa_link(w.phone, update_text(w, steps, url)) if has_dates else "",
           "wa_schedule_ml": wa_link(w.phone, schedule_text(w, ml_steps, url, "ml")) if has_dates else "",
           "wa_update_ml": wa_link(w.phone, update_text(w, ml_steps, url, "ml")) if has_dates else ""}
    return render(request, "portal/track_manage.html", ctx)


def _next_step(steps, t, today):
    nxt = next((s for s in steps if not s["done"] and s["planned"]), None) or next((s for s in steps if not s["done"]), None)
    if nxt is None:
        return None
    when = ""
    if nxt["planned"]:
        days = (nxt["planned"] - today).days
        when = t["overdue"] if days < 0 else (t["today"] if days == 0 else (t["tomorrow"] if days == 1 else t["in_days"] % days))
    return {"label": nxt["label"], "planned": nxt["planned"], "when": when}


def _system_rows(w, t):
    rows = []
    if w.kw:
        rows.append((t["capacity"], "%s kW" % w.kw))
    if w.panel_make or w.panel_count:
        rows.append((t["panels"], " x ".join(str(x) for x in (w.panel_count, w.panel_make) if x)))
    if w.inverter_make:
        rows.append((t["inverter"], w.inverter_make))
    if w.system:
        rows.append((t["type"], w.system))
    if w.project_id:
        rows.append((t["project_id"], w.project_id))
    if w.location:
        rows.append((t["place"], w.location))
    return rows


@login_not_required
def public(request, token):
    """What the customer sees.  Found only by the long private code in the link."""
    if not token or len(token) < 16:
        raise Http404
    w = ProjectWork.objects.filter(track_token=token).first()
    if w is None:
        raise Http404
    lang, today = _lang(request), timezone.localdate()
    t = TEXT[lang]
    steps = steps_of(w, today, lang)
    n_done = sum(1 for s in steps if s["done"])
    user = request.user
    back = reverse_manage(w) if (getattr(user, "is_authenticated", False) and project_work.can_edit(user)) else ""
    response = render(request, "portal/track_public.html", {
        "w": w, "steps": steps, "n_done": n_done, "n_all": len(steps), "pct": int(n_done * 100 / len(steps)), "t": t, "lang": lang,
        "next": _next_step(steps, t, today), "system": _system_rows(w, t), "contact": CONTACT_PHONE, "engineer": w.engineer, "today": today, "back": back,
        "wa_contact": wa_link(CONTACT_PHONE, t["wa_hello"] % (w.name, w.project_id or "-"))})
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    if request.GET.get("lang") in TEXT:
        response.set_cookie("track_lang", request.GET["lang"], max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def reverse_manage(w):
    from django.urls import reverse
    return reverse("progress_customer", args=[w.pk])
