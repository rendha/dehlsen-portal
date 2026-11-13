"""Payment collection: how much of the sold projects' price is collected and how much is still to collect, per person and per region.
Data = portal.Collection (loaded from the payment sheet, edited in Admin).  A person sees his own projects; a director sees everybody."""
from decimal import Decimal
from difflib import SequenceMatcher

from quotations import dashboard_stats as stats

from . import sales
from .models import Collection


def is_mine(keys, sales_name):
    """True when the sheet's name is this person: same name, or a close spelling (Huda / Hudha, Fouzan / Fousan)."""
    k = stats.name_key(sales_name)
    if not k:
        return False
    return any(k == m or SequenceMatcher(None, k, m).ratio() >= 0.8 for m in keys)


def _line(name):
    return {"name": name, "projects": 0, "kw": Decimal(0), "net": Decimal(0), "got": Decimal(0), "sub": {}}


def _finish(lines):
    out = []
    for l in lines.values():
        l["left"] = l["net"] - l["got"]
        l["percent"] = int((l["got"] / l["net"] * 100).to_integral_value()) if l["net"] > 0 else 0
        l["bar"] = max(0, min(l["percent"], 100))
        for k in ("net", "got", "left"):
            l[k + "_short"] = sales.short(l[k])
            l[k + "_text"] = sales.indian(l[k])
        l["sub_list"] = sorted(({"name": n, "got_short": sales.short(s["got"]), "left_short": sales.short(s["net"] - s["got"])} for n, s in l["sub"].items()),
                               key=lambda x: x["name"])
        out.append(l)
    out.sort(key=lambda l: -l["left"])          # most still to collect first
    return out


def build(user, director, person="", region=""):
    """-> dict: the whole company's total and every region (for everybody), the people (a director sees all, a sales person himself),
    and the customers with money still to collect (a director all of them, a sales person his own; person / region filter them)."""
    all_rows = list(Collection.objects.prefetch_related("payments__entered_by"))
    if director:
        mine_rows = all_rows
    else:
        keys = sales.keys_of(user)
        mine_rows = [r for r in all_rows if is_mine(keys, r.sales_name)]
    people, regions, total, mine = {}, {}, _line("Total"), _line("Mine")
    projects = []

    def add(line, r):
        line["projects"] += 1; line["kw"] += r.kw; line["net"] += r.net_value; line["got"] += r.received

    for r in all_rows:
        reg = r.region or "No region"
        l = regions.setdefault(reg, _line(reg))
        add(l, r); add(total, r)
        s = l["sub"].setdefault(r.sales_name, {"net": Decimal(0), "got": Decimal(0)})
        s["net"] += r.net_value; s["got"] += r.received
    mine_ids = {r.pk for r in mine_rows}
    for r in mine_rows:
        reg = r.region or "No region"
        l = people.setdefault(r.sales_name, _line(r.sales_name))
        add(l, r); add(mine, r)
        s = l["sub"].setdefault(reg, {"net": Decimal(0), "got": Decimal(0)})
        s["net"] += r.net_value; s["got"] += r.received
        if (not person or r.sales_name == person) and (not region or reg == region):
            projects.append({"pk": r.pk, "payments": [{"amount": sales.indian(x.amount), "date": x.date.strftime("%d %b %Y") if x.date else "no date", "stage": x.get_stage_display(),
                                                       "by": (x.entered_by.get_full_name() or x.entered_by.get_username()) if x.entered_by else "", "id": x.id}
                                                      for x in r.payments.all()[:6]],
                             "id": r.project_id, "info": " \u00b7 ".join(x for x in (r.segment, r.system_type, r.almm, r.panel, r.inverter, r.work_status) if x),
                             "customer": r.customer, "region": reg, "person": r.sales_name, "net": sales.indian(r.net_value),
                             "got": sales.indian(r.received), "left": r.balance, "left_text": sales.indian(r.balance),
                             "date": r.booking_date.strftime("%d %b %Y") if r.booking_date else ""})
    projects.sort(key=lambda p: -p["left"])
    return {"total": _finish({"t": total})[0], "mine": _finish({"m": mine})[0], "by_person": _finish(people), "by_region": _finish(regions),
            "projects": [p for p in projects if p["left"] > 0], "pending_count": len([p for p in projects if p["left"] > 0]),
            "person": person, "region": region}


def _place_of(sales_name, location):
    """The region of a confirmed quotation: the sales area of the person (Profile.place) when known, else the quotation's location."""
    from django.contrib.auth import get_user_model
    key = stats.name_key(sales_name)
    for u in get_user_model().objects.filter(is_active=True).select_related("portal_profile"):
        profile = getattr(u, "portal_profile", None)
        if profile and profile.place_id and key in sales.keys_of(u):
            return profile.place.name
    return (location or "").strip().title()


def _find(quotation):
    """The collection of this client: by the quotation, else by the same person + client name (it may come from the sheet)."""
    found = Collection.objects.filter(quotation_id=quotation.id).first()
    if found:
        return found
    person, client = stats.name_key(quotation.customer_name), stats.name_key(quotation.business_name)
    for c in Collection.objects.all():
        if stats.name_key(c.sales_name) == person and stats.name_key(c.customer) == client:
            return c
    return None


def sync_quotation(quotation):
    """A quotation became a customer: make (or update) its payment record.  Money already received is never touched.  -> the Collection or None."""
    try:
        price = quotation.final_quotation_price or 0
        c = _find(quotation)
        if c is None:
            c = Collection(project_id="Q-%s" % quotation.offer_no, received=0)
        c.quotation_id = quotation.id
        c.booking_date = c.booking_date or quotation.date
        c.customer = c.customer or (quotation.business_name or quotation.customer_name)
        c.sales_name = c.sales_name or quotation.customer_name
        c.region = c.region or _place_of(quotation.customer_name, quotation.location)
        c.kw = quotation.system_size or c.kw
        c.net_value = price
        c.save()
        return c
    except Exception:       # the payment record must never stop a customer from being confirmed
        return None


def unsync_quotation(quotation):
    """The customer was un-confirmed: drop the payment record only when nothing was received on it."""
    try:
        Collection.objects.filter(quotation_id=quotation.id, received=0).delete()
    except Exception:
        pass


def can_edit(user, collection, director):
    """The sales person of this customer (or a director) may add payments to it."""
    return bool(director or is_mine(sales.keys_of(user), collection.sales_name))
