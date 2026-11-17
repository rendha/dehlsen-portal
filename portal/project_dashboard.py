"""The project dashboard: counts, capacity, stages, KSEB alerts, equipment, contractors, handover and data completeness - all from the project records."""
import datetime
from collections import Counter, OrderedDict, defaultdict
from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from . import project_work as pw

STAGES = ["Not Updated", "Booked", "Feasibility Pending", "Feasibility Approved", "Material Dispatched", "Installation In Progress", "Structure Work", "Panel Fixing",
          "Electrical Work", "Inverter / Final Connection", "Installation Complete", "Net Meter / Inspection", "Commissioned", "On Hold", "Cancelled"]
REG_DAYS, WORK_DAYS, SOON, SUBSIDY_DAYS, METER_DAYS = 30, 30, 7, 30, 15


def num(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def kdate(w, key):
    if key == "feasibility":
        return w.feasibility_date
    if key == "commissioning":
        return w.commission_date
    try:
        return datetime.date.fromisoformat((w.kseb or {}).get(key) or "")
    except ValueError:
        return None


def stage_of(w):
    """One of the 15 stages: On Hold / Cancelled as entered, otherwise worked out from the ticks and dates, else the stage typed in the master."""
    ps = w.project_stage or ""
    if ps in ("On Hold", "Cancelled"):
        return ps
    if w.commission_date or (w.testing and w.meter_fix):
        return "Commissioned"
    if w.testing:
        return "Net Meter / Inspection"
    if w.inv_program:
        return "Installation Complete"
    if w.electrical:
        return "Electrical Work"
    if w.structure:
        return "Structure Work"
    if w.panel_done or w.inverter_done or w.bos:
        return "Material Dispatched"
    if w.design or w.site_estimation or w.feasibility_date:
        return "Feasibility Approved"
    return ps if ps in STAGES else "Booked"


def _pending(v):
    return (v or "").strip().lower() in ("yes", "required", "pending", "y")


def is_loan(w):
    return w.payment_mode == "loan"


def feas_applied(w):
    """Applied to KSEB (portal application or documents done, or the stage says Feasibility Pending) and the feasibility is not approved yet."""
    if w.commission_date or w.feasibility_date or (w.project_stage or "") in ("On Hold", "Cancelled", "Commissioned"):
        return False
    return (w.project_stage or "") == "Feasibility Pending" or bool(kdate(w, "portal_app") or kdate(w, "docs"))


FILTERS = {
    "loan": ("Bank loan customers", is_loan),
    "feas": ("Feasibility applied - waiting for KSEB approval", feas_applied),
    "name": ("Name change pending", lambda w: _pending(w.name_change)),
    "load": ("Load change pending", lambda w: _pending(w.load_change)),
    "nameload": ("Name change or load change pending", lambda w: _pending(w.name_change) or _pending(w.load_change)),
    "hold": ("Projects on hold", lambda w: (w.project_stage or "") == "On Hold"),
}


def build(rows, today=None):
    today = today or timezone.localdate()
    ws = [r["w"] for r in rows]
    n = len(ws)
    kw = lambda w: num(w.kw)
    st = {w.pk: stage_of(w) for w in ws}
    done = lambda w: st[w.pk] in ("Commissioned",)
    out = {"n": n, "today": today}
    out["kw_total"] = sum(kw(w) for w in ws)
    out["commissioned"] = sum(1 for w in ws if st[w.pk] == "Commissioned")
    out["net_meter"] = sum(1 for w in ws if st[w.pk] in ("Installation Complete", "Net Meter / Inspection"))
    out["in_progress"] = sum(1 for w in ws if st[w.pk] in ("Installation In Progress", "Structure Work", "Panel Fixing", "Electrical Work", "Inverter / Final Connection", "Material Dispatched"))
    out["booked"] = sum(1 for w in ws if st[w.pk] in ("Booked", "Feasibility Pending", "Feasibility Approved"))
    out["on_hold"] = sum(1 for w in ws if st[w.pk] == "On Hold")
    out["loan"] = sum(1 for w in ws if is_loan(w))
    out["feas_applied"] = sum(1 for w in ws if feas_applied(w))
    out["name_pending"] = sum(1 for w in ws if _pending(w.name_change))
    out["load_pending"] = sum(1 for w in ws if _pending(w.load_change))
    out["nameload_pending"] = sum(1 for w in ws if _pending(w.name_change) or _pending(w.load_change))
    out["value"] = sum(float((r["qv"]["deal"] or r["qv"]["quotation"] or r["w"].quote_value or 0)) for r in rows)
    # capacity
    out["dc_total"] = sum(num(w.dc_kwp) for w in ws)
    out["dc_done"] = sum(num(w.dc_kwp) for w in ws if done(w))
    out["ac_total"] = sum(num(w.ac_kw) for w in ws)
    out["ac_done"] = sum(num(w.ac_kw) for w in ws if done(w))
    out["dc_have"], out["ac_have"] = sum(1 for w in ws if w.dc_kwp), sum(1 for w in ws if w.ac_kw)
    # 1 stages
    sc = OrderedDict((s, [0, 0.0]) for s in STAGES)
    for w in ws:
        sc[st[w.pk]][0] += 1
        sc[st[w.pk]][1] += kw(w)
    out["stages"] = [(s, c, k, (c * 100.0 / n) if n else 0) for s, (c, k) in sc.items()]
    # 2 bookings by month (financial year from April of the report year)
    fy = today.year if today.month >= 4 else today.year - 1
    months = OrderedDict()
    for i in range(12):
        m = 4 + i
        y = fy + (m - 1) // 12
        months[(y, (m - 1) % 12 + 1)] = [0, 0.0]
    for w in ws:
        if w.booking_date and (w.booking_date.year, w.booking_date.month) in months:
            months[(w.booking_date.year, w.booking_date.month)][0] += 1
            months[(w.booking_date.year, w.booking_date.month)][1] += kw(w)
    out["months"] = [(datetime.date(y, m, 1), c, k) for (y, m), (c, k) in months.items()]
    # 3 and 5: simple group tables
    def group(attr, label=lambda x: x):
        g = defaultdict(lambda: [0, 0.0])
        for w in ws:
            key = (getattr(w, attr) or "").strip() or "Not set"
            g[key][0] += 1
            g[key][1] += kw(w)
        return sorted(((label(k), c, kk) for k, (c, kk) in g.items()), key=lambda t: (-t[1], t[0]))
    out["regions"], out["segments"], out["almm"], out["systems"] = group("region"), group("segment"), group("almm"), group("system")
    out["panels"], out["inverters"] = group("panel_make"), group("inverter_make")
    sales = defaultdict(lambda: [0, 0.0])
    for r in rows:
        o = r["owner"] or "Not set"
        sales[o][0] += 1
        sales[o][1] += kw(r["w"])
    out["sales"] = sorted(((k, c, kk) for k, (c, kk) in sales.items()), key=lambda t: (-t[1], t[0]))
    # 6 data completeness
    checks = [("Customer phone", lambda w: w.phone), ("Email", lambda w: w.email), ("Site address", lambda w: w.site_address), ("Pincode", lambda w: w.pincode),
              ("Google Map link", lambda w: w.map_link), ("KSEB consumer no.", lambda w: w.kseb_consumer_no), ("Panel brand", lambda w: w.panel_make),
              ("No. of panels", lambda w: w.panel_count), ("Panel wattage", lambda w: w.panel_wp), ("Inverter brand", lambda w: w.inverter_make),
              ("Quote value", lambda w: w.quote_value), ("Site in-charge", lambda w: w.engineer), ("Inverter serial no.", lambda w: w.inverter_serial),
              ("Energy meter serial no.", lambda w: w.energy_meter_serial), ("Net meter serial no.", lambda w: w.net_meter_serial),
              ("Panel serial numbers", lambda w: w.panel_serials)]
    out["complete"] = [(label, sum(1 for w in ws if fn(w)), n - sum(1 for w in ws if fn(w)), (sum(1 for w in ws if fn(w)) * 100.0 / n) if n else 0) for label, fn in checks]
    # 7 time frame
    def avg(a, b, get_a=None, get_b=None):
        vals = []
        for w in ws:
            x, y = (get_a(w) if get_a else kdate(w, a)), (get_b(w) if get_b else kdate(w, b))
            if x and y and y >= x:
                vals.append((y - x).days)
        return (sum(vals) / len(vals) if vals else None, len(vals))
    book = lambda w: w.booking_date
    out["frames"] = [("Booking > Feasibility approval", avg(None, "feasibility", book, None), "-"), ("Feasibility > Work start", avg("feasibility", "work_start"), "-"),
                     ("Work duration (start > completion)", avg("work_start", "work_done"), "-"), ("Feasibility > Work completion", avg("feasibility", "work_done"), WORK_DAYS),
                     ("Work completion > Net meter fixed", avg("work_done", "meter_fix"), METER_DAYS), ("Feasibility > Commissioning", avg("feasibility", "commissioning"), "-"),
                     ("Booking > Commissioning (total cycle)", avg(None, "commissioning", book, None), "-")]
    # 8 alerts
    A = OrderedDict((k, []) for k in ["Registration fee OVERDUE", "Registration fee due soon", "Work overdue vs target", "Work completed - net meter not fixed",
                                      "Net meter fixed - programming pending", "Commissioned - subsidy not credited", "Handover due (invoice + warranty)",
                                      "Panel count does not match serial numbers"])
    for w in ws:
        s = st[w.pk]
        fe = kdate(w, "feasibility")
        if fe and not w.registration_paid and not kdate(w, "reg_paid") and s not in ("Commissioned", "Cancelled", "On Hold"):
            left = (fe + datetime.timedelta(days=REG_DAYS) - today).days
            if left < 0:
                A["Registration fee OVERDUE"].append(w)
            elif left <= SOON:
                A["Registration fee due soon"].append(w)
        if fe and not kdate(w, "work_done") and s not in ("Commissioned", "Cancelled", "On Hold") and (fe + datetime.timedelta(days=WORK_DAYS) - today).days < 0:
            A["Work overdue vs target"].append(w)
        if kdate(w, "work_done") and not kdate(w, "meter_fix") and s != "Commissioned":
            A["Work completed - net meter not fixed"].append(w)
        if kdate(w, "meter_fix") and not kdate(w, "programming") and s != "Commissioned":
            A["Net meter fixed - programming pending"].append(w)
        if s == "Commissioned" and not kdate(w, "subsidy") and "subsidy" in (w.scheme or "").lower():
            A["Commissioned - subsidy not credited"].append(w)
        if s == "Commissioned" and not (w.handover or (w.handover_status or "").lower() == "handed over"):
            A["Handover due (invoice + warranty)"].append(w)
        if w.panel_count and w.panel_serials and len(pw.panel_serial_list(w)) != w.panel_count:
            A["Panel count does not match serial numbers"].append(w)
    out["alerts"] = [(k, len(v), [x.name for x in v][:6]) for k, v in A.items()]
    out["alert_counts"] = {k: len(v) for k, v in A.items()}
    # 9 handover
    handed = [w for w in ws if w.handover or (w.handover_status or "").lower() == "handed over"]
    out["handover"] = [("Handed over (invoice + warranty given)", len(handed)), ("Due for handover (commissioned, not handed over)", len(A["Handover due (invoice + warranty)"])),
                       ("Invoice number recorded", sum(1 for w in ws if w.invoice_no)),
                       ("Warranty period recorded (panel / inverter)", sum(1 for w in ws if w.panel_warranty_yrs or w.inverter_warranty_yrs))]
    soon = 0
    for w in ws:
        try:
            for _label, d in pw.warranty_list(w):
                if d and 0 <= (d - today).days <= 90:
                    soon += 1
        except Exception:
            pass
    out["handover"].append(("Warranties expiring in the next 90 days", soon))
    # contractors
    ct = {"Electrical": [Decimal(0), Decimal(0)], "Structure": [Decimal(0), Decimal(0)]}
    per = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for w in ws:
        ct["Electrical"][0] += w.electrical_amount or 0
        ct["Electrical"][1] += w.electrical_paid or 0
        ct["Structure"][0] += w.structure_amount or 0
        ct["Structure"][1] += w.structure_paid or 0
        if w.electrical_contractor:
            per[w.electrical_contractor.strip().title()][0] += w.electrical_amount or 0
            per[w.electrical_contractor.strip().title()][1] += w.electrical_paid or 0
        if w.structure_contractor:
            per[w.structure_contractor.strip().title()][0] += w.structure_amount or 0
            per[w.structure_contractor.strip().title()][1] += w.structure_paid or 0
    out["contractors"] = [(k, a, p, a - p) for k, (a, p) in ct.items()]
    out["per_contractor"] = sorted(((k, a, p, a - p) for k, (a, p) in per.items()), key=lambda t: -t[3])
    out["contractor_total"] = (sum(v[0] for v in ct.values()), sum(v[1] for v in ct.values()))
    return out


def dashboard(request):
    rows = pw._rows_for(request)
    return render(request, "portal/project_dashboard.html", {"d": build(rows), "can_edit": pw.can_edit(request.user)})


DOC_NAMES = ["Invoice", "Warranty Certificate", "Panel Datasheet", "Inverter Datasheet", "Commissioning Certificate", "Net Metering Agreement", "Monitoring App Login", "User Manual"]


def _handed(w):
    return bool(w.handover or (w.handover_status or "").lower() == "handed over")


def commissioned(request):
    """Commissioned customers with their subsidy tracking and handover / documents."""
    today = timezone.localdate()
    rows = pw._rows_for(request)
    items = []
    for r in rows:
        w = r["w"]
        if stage_of(w) != "Commissioned":
            continue
        start = w.commission_date or kdate(w, "commissioning")
        has_subsidy = "subsidy" in (w.scheme or "").lower()
        credited = kdate(w, "subsidy")
        waiting = (today - start).days if (start and has_subsidy and not credited) else None
        docs = {n: (str((w.docs_given or {}).get(n, "")).strip().lower().startswith("y")) for n in DOC_NAMES}
        wl = pw.warranty_list(w)
        items.append({
            "w": w, "start": start, "scheme": w.scheme or "-", "has_subsidy": has_subsidy, "credited": credited, "waiting": waiting,
            "sub_status": w.subsidy_status or ("Credited" if credited else ("Pending" if has_subsidy else "Not applicable")),
            "late": waiting is not None and waiting > SUBSIDY_DAYS, "bank": (w.bank_details or "").strip(),
            "handed": _handed(w), "docs": docs, "docs_n": sum(docs.values()), "warranty": wl[0][1] if wl else None,
            "sub_pending": has_subsidy and not credited, "owner": r["owner"],
        })
    items.sort(key=lambda i: (i["start"] or datetime.date.min))
    counts = {"all": len(items), "subsidy": sum(1 for i in items if i["sub_pending"]), "handover": sum(1 for i in items if not i["handed"]),
              "docs": sum(1 for i in items if i["docs_n"] < len(DOC_NAMES))}
    show = request.GET.get("show") if request.GET.get("show") in counts else "all"
    pick = {"all": lambda i: True, "subsidy": lambda i: i["sub_pending"], "handover": lambda i: not i["handed"], "docs": lambda i: i["docs_n"] < len(DOC_NAMES)}[show]
    q = (request.GET.get("q") or "").strip().lower()
    shown = [i for i in items if pick(i) and (not q or q in (i["w"].name + " " + (i["w"].phone or "") + " " + (i["w"].project_id or "") + " " + (i["w"].location or "")).lower())]
    return render(request, "portal/project_commissioned.html", {"items": shown, "counts": counts, "show": show, "q": q, "total": len(shown), "n_docs": len(DOC_NAMES),
                                                                  "tabs": [("all", "All commissioned"), ("subsidy", "Subsidy pending"), ("handover", "Handover pending"), ("docs", "Documents incomplete")]})
