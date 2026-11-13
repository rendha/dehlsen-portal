"""Sales targets of places (Kochi, Kannur, Kozhikode and others) and of single persons.

Achieved = the final price (GST included) of the CONFIRMED customers (Quotation.is_customer) dated inside the period, one per client
(dashboard_stats.summarize_clients).  A place adds up its people; a person is matched by the name typed in "Quotation For" = Profile.sales_name,
else his first name, else his username.  A target with "fixed achieved" filled (a finished quarter) uses that number instead.
The year's achieved = the achieved of its quarters (so the fixed ones are kept); a year without quarters is counted directly.
The quarter targets already carry any shortfall of the earlier quarters, so the year shows how far from the yearly target.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from quotations import dashboard_stats as stats
from quotations.models import Quotation

from .models import SalesTarget


def _label(user):
    return user.get_full_name() or user.get_username()


def keys_of(user):
    profile = getattr(user, "portal_profile", None)
    names = [getattr(profile, "sales_name", ""), user.first_name, user.get_username()]
    return {stats.name_key(n) for n in names if n and n.strip()}


def people_of(t):
    if t.place_id:
        return [p.user for p in t.place.members.select_related("user") if p.user.is_active]
    return [t.user]


def count(people, start, end):
    """-> (value, customers) of these people inside the dates: the sold value (price after discount) of their projects in the
    payment collection list (portal.Collection: loaded from the sheet, and added automatically when a quotation is confirmed), by booking date."""
    from . import payments
    from .models import Collection
    keys = set()
    for u in people:
        keys |= keys_of(u)
    value, clients = Decimal(0), 0
    for c in Collection.objects.filter(booking_date__gte=start, booking_date__lte=end):
        if payments.is_mine(keys, c.sales_name):
            value += Decimal(c.net_value)
            clients += 1
    return value, clients


def is_year(t):
    return (t.end_date - t.start_date).days > 120          # longer than ~4 months = the "year" (a part-year such as Oct-Mar too), shorter = a quarter


def same_owner(a, b):
    return (a.place_id, a.user_id) == (b.place_id, b.user_id)


def achieved(t, all_targets):
    """-> (value, customers) of one target."""
    if t.fixed_achieved is not None:
        return Decimal(t.fixed_achieved), None
    if is_year(t):
        quarters = [q for q in all_targets if not is_year(q) and same_owner(q, t) and q.start_date >= t.start_date and q.end_date <= t.end_date]
        if quarters:
            total, customers = Decimal(0), 0
            for q in quarters:
                v, c = achieved(q, all_targets)
                total += v
                customers += c or 0
            return total, customers
    return count(people_of(t), t.start_date, t.end_date)


def indian(value):
    return "₹" + stats.indian(value)


def short(value):
    """12,50,000 -> '12.5 L',  1,30,00,000 -> '1.3 Cr' (easy to read)."""
    value = Decimal(value)
    if abs(value) >= 10000000:
        return ("%.2f" % (value / 10000000)).rstrip("0").rstrip(".") + " Cr"
    if abs(value) >= 100000:
        return ("%.2f" % (value / 100000)).rstrip("0").rstrip(".") + " L"
    return stats.indian(value)


def make_line(t, all_targets, today):
    got, customers = achieved(t, all_targets)
    target = Decimal(t.amount)
    percent = (got / target * 100) if target > 0 else Decimal(0)
    total_days = (t.end_date - t.start_date).days + 1
    time_percent = max(0, min(100, int((today - t.start_date).days + 1) * 100 // total_days))
    line = {
        "key": ("p", t.place_id) if t.place_id else ("u", t.user_id), "name": t.who, "is_place": bool(t.place_id),
        "label": t.label or "%s to %s" % (t.start_date.strftime("%d %b %Y"), t.end_date.strftime("%d %b %Y")),
        "target": target, "target_text": indian(target), "target_short": short(target), "got": got, "got_text": indian(got), "got_short": short(got),
        "left_text": indian(max(target - got, Decimal(0))), "left_short": short(max(target - got, Decimal(0))),
        "over": max(got - target, Decimal(0)), "over_text": indian(max(got - target, Decimal(0))), "over_short": short(max(got - target, Decimal(0))),
        "percent": int(percent.to_integral_value()), "bar": min(int(percent), 100), "customers": customers,
        "days_left": (t.end_date - today).days, "time_percent": time_percent, "ends": t.end_date.strftime("%d %b %Y"),
        "ended": t.end_date < today, "started": t.start_date <= today,
    }
    line["behind"] = line["over"] == 0 and line["percent"] < time_percent and not line["ended"]
    return line


def build(today=None):
    """-> {"quarter": [lines], "year": [lines]}, each best first.  Every line of a place/person also carries its quarter-by-quarter table and its people."""
    today = today or timezone.localdate()
    all_targets = list(SalesTarget.objects.select_related("place", "user", "user__portal_profile"))
    out = {"quarter": [], "year": []}
    for kind in ("quarter", "year"):
        current = {}
        for t in all_targets:
            if is_year(t) != (kind == "year") or not (t.start_date <= today <= t.end_date):
                continue
            if t.user_id and not t.user.is_active:
                continue
            k = (t.place_id, t.user_id)
            if k not in current or t.end_date > current[k].end_date:
                current[k] = t
        for t in current.values():
            line = make_line(t, all_targets, today)
            if kind == "year":
                line["quarters"] = []
                for q in sorted((q for q in all_targets if not is_year(q) and same_owner(q, t) and q.start_date >= t.start_date and q.end_date <= t.end_date),
                                key=lambda q: q.start_date):
                    ql = make_line(q, all_targets, today)
                    ql["state"] = "done" if q.end_date < today else ("now" if q.start_date <= today else "next")
                    line["quarters"].append(ql)
            if t.place_id:
                line["members"] = [{"name": _label(u), "got_short": short(count([u], t.start_date, t.end_date)[0])} for u in people_of(t)]
            out[kind].append(line)
        out[kind].sort(key=lambda l: (-l["percent"], l["name"].lower()))
        for i, l in enumerate(out[kind], 1):
            l["rank"] = i
    company = {}
    for kind in ("quarter", "year"):
        lines = [l for l in out[kind] if l["is_place"]] or out[kind]
        target = sum((l["target"] for l in lines), Decimal(0))
        got = sum((l["got"] for l in lines), Decimal(0))
        company[kind] = {"target_short": short(target), "got_short": short(got), "percent": int((got / target * 100).to_integral_value()) if target else 0,
                         "bar": min(int((got / target * 100)) if target else 0, 100),
                         "target_text": indian(target), "got_text": indian(got), "left_short": short(max(target - got, Decimal(0))), "over_short": short(max(got - target, Decimal(0))), "over": got > target}
    return out, company


def for_user(user, today=None, previous=False):
    """-> [{key, title, mine, board, company}] for the quarter and the year.  `mine` = the line of his place (or of himself).
    previous=True -> only the quarter before the current one (as it ended)."""
    if previous:
        import datetime
        today = today or timezone.localdate()
        cur = [t for t in SalesTarget.objects.all() if not is_year(t) and t.start_date <= today <= t.end_date]
        if not cur:
            return []
        today = min(t.start_date for t in cur) - datetime.timedelta(days=1)
    lines, company = build(today)
    profile = getattr(user, "portal_profile", None)
    my_keys = {("u", user.id)}
    if profile is not None and profile.place_id:
        my_keys.add(("p", profile.place_id))
    result = []
    for key, title in ((("quarter", "Previous quarter"),) if previous else (("year", "Overall target: this year"), ("quarter", "This quarter"))):
        if not lines[key]:
            continue
        mine = next((l for l in lines[key] if l["key"] in my_keys), None)
        result.append({"title": title, "mine": mine, "board": lines[key], "company": company[key], "kind": key})
    return result
