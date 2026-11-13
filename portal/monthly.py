"""The extra sections of the monthly report (portal only): sales, collections, regions, people, targets, lead conversion, service and low-margin quotations.
Every block is built on its own and is None when it fails, so one problem never breaks the report."""
import datetime
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum

from . import dashboard, sales
from .models import Collection, Payment


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _month_end(first):
    nxt = datetime.date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1)


def _prev_first(first):
    return (first - datetime.timedelta(days=1)).replace(day=1)


def _sold(first):
    rows = list(Collection.objects.filter(booking_date__gte=first, booking_date__lte=_month_end(first)))
    return {"projects": len(rows), "kw": sum((r.kw for r in rows), Decimal(0)), "net": sum((r.net_value for r in rows), Decimal(0)),
            "got": sum((r.received for r in rows), Decimal(0)), "rows": rows}


def _change(now, before):
    if not before:
        return ""
    pct = (Decimal(now) - Decimal(before)) * 100 / Decimal(before)
    return "%s%d%% vs last month" % ("+" if pct >= 0 else "", int(pct))


def _group(rows, key):
    out = OrderedDict()
    for r in rows:
        g = out.setdefault(key(r) or "No region", {"projects": 0, "kw": Decimal(0), "net": Decimal(0), "got": Decimal(0)})
        g["projects"] += 1; g["kw"] += r.kw; g["net"] += r.net_value; g["got"] += r.received
    lines = []
    for name, g in out.items():
        left = g["net"] - g["got"]
        lines.append({"name": name, "projects": g["projects"], "kw": int(g["kw"]), "net": sales.short(g["net"]), "got": sales.short(g["got"]),
                      "left": sales.short(left), "percent": int((g["got"] * 100 / g["net"]).to_integral_value()) if g["net"] > 0 else 0, "_n": g["net"]})
    lines.sort(key=lambda l: -l["_n"])
    return lines


def build(first, today, quotation_rows_count=0):
    """-> the dict the template _monthly_extra.html prints."""
    last = min(_month_end(first), today)
    now = _sold(first)
    before = _sold(_prev_first(first))
    data = {}

    def headline():
        pending_now = sum((r.net_value - r.received for r in Collection.objects.filter(booking_date__lte=_month_end(first))), Decimal(0))
        got_month = Payment.objects.filter(date__gte=first, date__lte=_month_end(first)).aggregate(t=Sum("amount"))["t"] or Decimal(0)
        undated = Payment.objects.filter(date__isnull=True).count()
        return {"projects": now["projects"], "projects_change": _change(now["projects"], before["projects"]),
                "kw": int(now["kw"]), "kw_change": _change(now["kw"], before["kw"]),
                "net": sales.short(now["net"]), "net_change": _change(now["net"], before["net"]),
                "got_month": sales.short(got_month), "pending_now": sales.short(pending_now), "undated": undated}
    data["headline"] = _safe(headline)

    def collections():
        stages = []
        names = dict(Payment.STAGES)
        qs = Payment.objects.filter(date__gte=first, date__lte=_month_end(first)).values("stage").annotate(t=Sum("amount"))
        for row in qs:
            stages.append({"name": names.get(row["stage"], row["stage"]), "amount": sales.short(row["t"])})
        top = []
        for c in sorted(Collection.objects.all(), key=lambda c: c.net_value - c.received, reverse=True)[:10]:
            left = c.net_value - c.received
            if left > 0:
                top.append({"customer": c.customer, "person": c.sales_name, "region": c.region, "left": sales.indian(left), "got": sales.indian(c.received), "net": sales.indian(c.net_value)})
        return {"stages": stages, "top": top}
    data["collections"] = _safe(collections)
    data["regions"] = _safe(lambda: _group(now["rows"], lambda r: r.region))
    data["people"] = _safe(lambda: _group(now["rows"], lambda r: r.sales_name))

    def targets():
        out, company = sales.build(last)
        return {"lines": out["quarter"], "company": company["quarter"]}
    data["targets"] = _safe(targets)

    def funnel():
        from quotations.models import Quotation
        from .models import Lead
        leads = Lead.objects.filter(created_at__date__gte=first, created_at__date__lte=last).count()
        quoted = len(dashboard._clients(Quotation.objects.filter(date__gte=first, date__lte=last)))
        won = now["projects"]
        return {"leads": leads, "quoted": quoted, "won": won,
                "q_pct": dashboard._pct(quoted, leads) if leads else None, "w_pct": dashboard._pct(won, quoted) if quoted else None}
    data["funnel"] = _safe(funnel)
    data["service"] = _safe(lambda: dashboard._service_block(first, last, today))

    def margins():
        from quotations import low_margin
        return [r for r in low_margin.rows() if first <= r["date"] <= _month_end(first)]
    data["margins"] = _safe(margins)
    return data
