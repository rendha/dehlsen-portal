"""Project progress: where every customer's installation stands (stage ticks), what payment that makes due, and who may update it.
Fidha and Riswan tick the stages; directors see everything; a sales person sees the projects of his own customers."""
import datetime
import re
from decimal import Decimal
from difflib import SequenceMatcher

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import payments, sales
from .models import Collection, ProjectWork

EDITORS = {"fidha", "riswan"}                     # the only people who tick stages and update a project (user name or first name)
TABS = [("live", "Live"), ("risk", "At risk"), ("bank", "Bank pending"), ("finished", "Finished"), ("docs", "Waiting documents"), ("pay", "Payment pending"), ("feas", "Feasibility issue"), ("unbooked", "Not booked yet"), ("all", "All")]
EXPOSURE_RED = Decimal("25000")          # material at site worth this much more than the money received = red (below that, amber)
BANK_LATE_DAYS = 15                      # the bank's final payment is late this many days after commissioning
WORK_GATE = ("bos", "inverter_done", "panel_done", "electrical", "structure")   # physical work: a loan project waits for the bank's first payment
SWITCH_GATE = ("testing", "meter_fix")   # switching on: a loan customer pays his own share first
STAGE_KEYS = [k for k, _l in ProjectWork.STAGES]


def can_edit(user):
    names = {(user.get_username() or "").lower(), (user.first_name or "").lower()}
    return bool(names & EDITORS) or bool(getattr(user, "is_superuser", False)) or _director(user)


def _director(user):
    from .views import _is_director
    return _is_director(user)


def value_of(w, cust, quotation_value):
    """The price this customer pays: the DEAL value (after discount) of the payment sheet when there is one, else the quotation's value
    (from the quotation app, or the store's copy of it).  None when we know neither."""
    c = w.collection if w.collection_id else None
    if c is not None and c.net_value:
        return c.net_value
    if quotation_value:
        return quotation_value
    if cust is not None and cust.total_due:
        return cust.total_due
    return None


def due_of(w, value, received):
    """What the customer should already have paid because of the work done: advance 20% from the start, material 50% once BOS, inverter and
    panel are in, installation 20% once electrical and structure work are done, handover 10% once testing and meter fix are done."""
    if not value:
        return None
    pct = 20
    if w.bos and w.inverter_done and w.panel_done:
        pct += 50
    if w.electrical and w.structure:
        pct += 20
    if w.testing and w.meter_fix:
        pct += 10
    due = (value * pct / 100).quantize(Decimal("1"))
    overdue = max(Decimal(0), due - received)
    return {"pct": pct, "due": due, "value": value, "received": received, "overdue": overdue, "balance": value - received}


def _issued_kind(name):
    """'panel', 'inverter' or '' for a store material line."""
    from store.services import default_gst
    n = (name or "").lower()
    if default_gst(name) != 5:
        return ""
    return "inverter" if ("inverter" in n or "kw" in n) else "panel"


def received_of(w, cust=None):
    """Money in: what the accounts sheet shows (else the payments typed in the store), plus the bank stages ticked here (so do not also enter bank money in the sheet)."""
    if w.collection_id:
        r = w.collection.received
    elif cust is not None:
        r = sum((p.amount for p in cust.payments.all()), Decimal(0))
    else:
        r = Decimal(0)
    if w.is_loan:
        if w.bank1_received_on:
            r += w.bank1_amount
        if w.bank2_received_on:
            r += w.bank2_amount
    return r


def exposure(w, cust):
    """Value of the material issued at the site (with GST) against the money received.  gap > 0 means we have given more than we were paid."""
    if cust is None:
        return None
    site = sum((l.amount_with_gst for l in cust.lines.all() if l.store_status == "done"), Decimal(0))
    got = received_of(w, cust)
    gap = site - got
    level = "ok" if gap <= 0 else ("red" if gap > EXPOSURE_RED else "amber")
    return {"site": site, "received": got, "gap": gap, "level": level}


def auto_ticks(w, cust):
    """Tick BOS / inverter / panel when the store has issued every such line of this customer.  Returns True when something was ticked."""
    if cust is None:
        return False
    lines = list(cust.lines.all())
    changed = False
    for key, test in (("bos", lambda l: l.group == "bos"), ("inverter_done", lambda l: _issued_kind(l.name) == "inverter"),
                      ("panel_done", lambda l: _issued_kind(l.name) == "panel")):
        mine = [l for l in lines if test(l)]
        if mine and not getattr(w, key) and all(l.store_status == "done" for l in mine):
            setattr(w, key, True)
            changed = True
    return changed


REG_DAYS, WORK_DAYS, METER_DAYS, SUBSIDY_DAYS, SOON_DAYS = 30, 30, 15, 30, 7      # the rules of the KSEB sheet's Settings (work and meter days are assumptions)


def _pd(v):
    try:
        return datetime.date.fromisoformat(v) if isinstance(v, str) and v else (v if isinstance(v, datetime.date) else None)
    except ValueError:
        return None


def kseb_date(w, key):
    if key == "feasibility":
        return w.feasibility_date
    if key == "commissioning":
        return w.commission_date
    return _pd((w.kseb or {}).get(key))


def kseb_steps(w):
    """The 12 steps with their dates, which are done, and the next one."""
    rows = []
    for key, label in ProjectWork.KSEB_STEPS:
        d = kseb_date(w, key)
        done = bool(d) or (key == "reg_paid" and w.registration_paid) or (key == "meter_fix" and w.meter_fix) or (key == "commissioning" and w.commissioned)
        rows.append({"key": key, "label": label, "date": d, "done": done})
    nxt = next((r["label"] for r in rows if not r["done"]), "")
    return rows, sum(1 for r in rows if r["done"]), nxt


MATERIAL_ITEMS = [("structure_mat", "Structure material", 20), ("panel_done", "Panel delivery", 30), ("bos", "BOS kit", 20), ("inverter_done", "Inverter delivery", 20), ("meter_mat", "Net meter", 10)]
WORK_ITEMS = [("site_estimation", "Site estimation", 5), ("design", "Design", 5), ("structure", "Structure work", 15), ("panel_mount", "Panel mounting", 25), ("electrical", "Electrical work", 20),
              ("earthing", "Earthing work", 10), ("meter_fix", "Net meter fixing", 10), ("testing", "Testing / programming / inspection", 10)]
PAPER_ITEMS = [("kp_feas", "KSEB feasibility", 30), ("kp_docs", "Document submission", 40), ("kp_meter", "Net meter submission", 20), ("kp_comm", "Commissioning", 10)]
NEW_KEYS = ("structure_mat", "meter_mat", "panel_mount", "earthing")
PAPER_KEYS = tuple(k for k, _l, _w in PAPER_ITEMS)
WORK_GATE = WORK_GATE + NEW_KEYS


def paper_done(w, key):
    if key == "kp_feas":
        return bool(w.feasibility_date) or w.feasibility == "ok"
    if key == "kp_docs":
        return bool(kseb_date(w, "docs"))
    if key == "kp_meter":
        return bool(kseb_date(w, "netmeter_app"))
    return w.commissioned


def _weighted(w, items, done=None):
    rows = [{"key": k, "label": l, "weight": wt, "on": bool(done(k) if done else getattr(w, k))} for k, l, wt in items]
    pct = sum(r["weight"] for r in rows if r["on"])
    left = [r["label"] for r in rows if not r["on"]]
    return {"pct": pct, "items": rows, "text": ("%d of %d done" % (sum(1 for r in rows if r["on"]), len(rows))) + ((" \u00b7 left: " + ", ".join(left[:2]) + ("..." if len(left) > 2 else "")) if left else "")}


def material_pct(w, cust=None):
    """Material delivered: structure material 20, panels 30, BOS kit 20, inverter 20, net meter 10 (percent of each ticked item added)."""
    return _weighted(w, MATERIAL_ITEMS)


def work_pct(w):
    """Site work: estimation 5, design 5, structure 15, panel mounting 25, electrical 20, earthing 10, net meter fixing 10, testing/programming/inspection 10."""
    return _weighted(w, WORK_ITEMS)


def paper_pct(w):
    """KSEB paperwork: feasibility 30, document submission 40, net meter submission 20, commissioning 10."""
    return _weighted(w, PAPER_ITEMS, lambda k: paper_done(w, k))


def handover_pct(w):
    from .project_dashboard import DOC_NAMES
    n = sum(1 for d in DOC_NAMES if str((w.docs_given or {}).get(d, "")).strip().lower().startswith("y"))
    return {"pct": int(round(n * 100 / len(DOC_NAMES))), "text": "%d of %d documents given" % (n, len(DOC_NAMES))}


def kseb_clocks(w, today):
    """Deadlines that follow from the dates.  Each: label, date, done, days left, late, soon."""
    feas, work_done, comm = w.feasibility_date, kseb_date(w, "work_done"), w.commission_date
    reg_done = bool(kseb_date(w, "reg_paid")) or w.registration_paid
    out = []
    if feas:
        out.append(("KSEB registration fee", feas + datetime.timedelta(days=REG_DAYS), reg_done))
        out.append(("Work completion", feas + datetime.timedelta(days=WORK_DAYS), bool(work_done) or w.commissioned))
    if work_done:
        out.append(("Net meter fixing", work_done + datetime.timedelta(days=METER_DAYS), bool(kseb_date(w, "meter_fix")) or w.meter_fix))
    if comm:
        out.append(("Subsidy follow-up", comm + datetime.timedelta(days=SUBSIDY_DAYS), bool(kseb_date(w, "subsidy"))))
    res = []
    for label, d, done in out:
        left = (d - today).days
        res.append({"label": label, "date": d, "done": done, "left": left, "late": left < 0 and not done, "soon": 0 <= left <= SOON_DAYS and not done})
    return res


def _plus_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d + datetime.timedelta(days=365 * n)


def warranty_list(w):
    """(label, expiry date) for workmanship (default 5 years), panels and inverter, counted from commissioning (else handover)."""
    start = w.commission_date or w.handover_date
    if not start:
        return []
    out = [("Workmanship", _plus_years(start, w.workmanship_yrs or 5))]
    if w.panel_warranty_yrs:
        out.append(("Panel product", _plus_years(start, w.panel_warranty_yrs)))
    if w.inverter_warranty_yrs:
        out.append(("Inverter", _plus_years(start, w.inverter_warranty_yrs)))
    return out


def warranty_end(w):
    lst = warranty_list(w)
    return lst[0][1] if lst else None


def panel_serial_list(w):
    return [s.strip() for s in (w.panel_serials or "").replace("\n", ",").split(",") if s.strip()]


def serial_problems(w, counter):
    """Messages about the serial numbers: missing, wrong count, or a number used by another project."""
    msgs = []
    serials = panel_serial_list(w)
    if w.panel_count and serials and len(serials) != w.panel_count:
        msgs.append("%d panel serials entered, %d panels" % (len(serials), w.panel_count))
    dup = [s for s in serials if counter.get(s, 0) > 1]
    if dup:
        msgs.append("Used twice: " + ", ".join(dup[:3]))
    return msgs


def gate_message(w, stage):
    """Why this stage cannot be ticked yet (loan projects), or ''."""
    if not w.is_loan:
        return ""
    if stage in WORK_GATE and not w.bank1_received_on:
        return "Bank loan: work starts only after the bank's first payment (Rs %s) is received. A director marks it received." % int(w.bank1_amount)
    if stage in SWITCH_GATE and w.collection_id:
        share = w.collection.net_value - w.loan_amount
        if w.collection.received < share:
            return "Bank loan: the customer's own share (Rs %s) must be paid before the plant is switched on. Paid so far: Rs %s." % (int(share), int(w.collection.received))
    return ""


def match_collection(name, collections):
    """The payment-sheet project of this customer: same cleaned name, else a very close spelling.  None when unsure."""
    from quotations import dashboard_stats as stats
    k = stats.name_key(name)
    if not k:
        return None
    best, hit = 0.0, None
    for c in collections:
        ck = stats.name_key(c.customer)
        s = 1.0 if ck == k else SequenceMatcher(None, k, ck).ratio()
        if s > best:
            best, hit = s, c
    return hit if best >= 0.88 else None


_ALIASES = {"meter_fix": "net meter", "inv_program": "programming", "bos": "balance of system", "structure": "structure", "site_estimation": "site visit"}


def stage_now(w):
    """Where the work is: the last stage ticked, and the stage that comes next (the first one not ticked yet).  (now_key, now_label, next_label)"""
    ticks = w.ticks
    last = max((i for i, (_k, _l, on) in enumerate(ticks) if on), default=-1)
    nxt = next((l for _k, l, on in ticks if not on), "")
    if last < 0:
        return "none", "Not started", nxt
    return ticks[last][0], ticks[last][1], nxt


def _owner(w):
    """Whose customer this is: the sales person from the Project List, else the one in the payment sheet."""
    return w.sales_person or (w.collection.sales_name if w.collection_id else "") or ""


def find_store_customer(w, by_quotation, skeys, stats):
    """The store customer (material list) of this project: by the quotation both came from, else by the same name."""
    qid = (w.collection.quotation_id if w.collection_id else None) or w.quotation_id
    if qid and qid in by_quotation:
        return by_quotation[qid]
    best, hit = 0.0, None
    for name in {w.name, w.collection.customer if w.collection_id else ""}:
        k = stats.name_key(name)
        if not k:
            continue
        for ck, c in skeys:
            s = 1.0 if ck == k else SequenceMatcher(None, k, ck).ratio()
            if s > best:
                best, hit = s, c
    return hit if best >= 0.88 else None


def quote_info(w, cust, qmap):
    """Quotation value from the quotation app (through the payment record's quotation), else the store's copy of it; and the deal value."""
    c = w.collection if w.collection_id else None
    q = qmap.get((c.quotation_id if c else None) or w.quotation_id)
    value, offer = None, ""
    if q is not None:
        value, offer = q["final_quotation_price"], q["offer_no"]
    elif cust is not None and cust.quoted_total:
        value, offer = cust.quoted_total, cust.offer_no
    return {"quotation": value, "offer": offer, "deal": c.net_value if c else None}


def _auto_projects():
    """A customer confirmed in the quotation app and not yet in the project list is added now (cheap check first)."""
    try:
        from quotations.models import Quotation
        from .project_sync import IGNORED_OFFERS, ensure_projects
        known = set(ProjectWork.objects.exclude(quotation_id=None).values_list("quotation_id", flat=True))
        known |= set(Collection.objects.exclude(quotation_id=None).filter(works__isnull=False).values_list("quotation_id", flat=True))
        missing = list(Quotation.objects.filter(is_customer=True).exclude(id__in=known).exclude(offer_no__in=IGNORED_OFFERS).values_list("id", flat=True))
        if missing:
            ensure_projects(quotation_ids=missing)
    except Exception:
        pass


def _rows_for(request):
    """One row per customer the person may see, with the money, the stage and the deadlines worked out.  -> rows"""
    _auto_projects()
    user = request.user
    editor, director = can_edit(user), _director(user)
    works = list(ProjectWork.objects.select_related("collection"))
    if not (editor or director):
        keys = sales.keys_of(user)
        works = [w for w in works if w.collection_id and payments.is_mine(keys, w.collection.sales_name)]
    from store.models import Customer as StoreCustomer
    store_customers = list(StoreCustomer.objects.prefetch_related("lines", "payments"))
    from quotations import dashboard_stats as stats
    skeys = [(stats.name_key(c.name), c) for c in store_customers]
    by_quotation = {c.quotation_id: c for c in store_customers if c.quotation_id}
    from quotations.models import Quotation
    qids = [(w.collection.quotation_id if w.collection_id else None) or w.quotation_id for w in works]
    qids = [i for i in qids if i]
    qmap = {q["id"]: q for q in Quotation.objects.filter(id__in=qids).values("id", "offer_no", "final_quotation_price")}
    today = timezone.localdate()
    rows = []
    for w in works:
        cust = find_store_customer(w, by_quotation, skeys, stats)
        if auto_ticks(w, cust):
            w.save(update_fields=["bos", "inverter_done", "panel_done"])
        qv = quote_info(w, cust, qmap)
        d = due_of(w, value_of(w, cust, qv["quotation"]), received_of(w, cust))
        ex = exposure(w, cust)
        bank_wait = w.is_loan and ((w.commissioned and not w.bank2_received_on) or (not w.bank1_received_on))
        bank_late = bool(w.is_loan and w.commissioned and not w.bank2_received_on and w.commission_date
                         and (today - w.commission_date).days > BANK_LATE_DAYS)
        rows.append({"w": w, "due": d, "finished": w.commissioned, "docs": w.commissioned and not w.handover,
                     "unbooked": bool(not w.project_id and not w.commissioned and (not w.collection_id or not (w.collection.received or 0))),
                     "pay": bool(d and (d["overdue"] > 0 or d["balance"] > 0)), "feas": w.feasibility == "issue",
                     "overdue": bool(d and d["overdue"] > 0), "ex": ex, "risk": bool(ex and ex["gap"] > 0 and not w.commissioned),
                     "now_key": stage_now(w)[0], "now": stage_now(w)[1], "next": stage_now(w)[2], "owner": _owner(w), "name": w.collection.customer if (w.collection_id and w.collection.customer) else w.name, "qv": qv, "bank": bank_wait, "bank_late": bank_late, "clocks": kseb_clocks(w, today), "warranty": warranty_end(w),
                     "kseb_done": kseb_steps(w)[1], "kseb_next": kseb_steps(w)[2],
                     "mat": material_pct(w, cust), "work": work_pct(w), "paper": paper_pct(w), "hand": handover_pct(w)})
    rows.sort(key=lambda r: (r["w"].booking_date or r["w"].commission_date or datetime.date.min, r["w"].project_id or ""), reverse=True)      # the latest won project first; no date last
    return rows


def progress(request):
    user = request.user
    editor, director = can_edit(user), _director(user)
    rows = _rows_for(request)
    tab = request.GET.get("tab") if request.GET.get("tab") in dict(TABS) else "live"      # the page opens on the Live tab (one row per stage)
    q = (request.GET.get("q") or "").strip().lower()
    counts = {"risk": sum(1 for r in rows if r["risk"]), "bank": sum(1 for r in rows if r["bank"]),
              "live": sum(1 for r in rows if not r["finished"]), "finished": sum(1 for r in rows if r["finished"]), "docs": sum(1 for r in rows if r["docs"]),
              "pay": sum(1 for r in rows if r["pay"]), "feas": sum(1 for r in rows if r["feas"]), "unbooked": sum(1 for r in rows if r["unbooked"]), "all": len(rows)}
    pick = {"risk": lambda r: r["risk"], "bank": lambda r: r["bank"], "live": lambda r: not r["finished"], "finished": lambda r: r["finished"], "docs": lambda r: r["docs"], "pay": lambda r: r["pay"],
            "feas": lambda r: r["feas"], "unbooked": lambda r: r["unbooked"], "all": lambda r: True}[tab]
    stage = request.GET.get("stage") if request.GET.get("stage") in set(STAGE_KEYS) | {"none", "done"} else ""

    def _hay(r):
        return " ".join([r["w"].name, r["name"], r["w"].location or "", r["w"].phone or "", _owner(r["w"]), r["now"], _ALIASES.get(r["now_key"], "")]).lower()
    from .project_dashboard import FILTERS, STAGES as STAGES15, stage_of
    st_pick = request.GET.get("st") if request.GET.get("st") in STAGES15 else ""
    st_counts = {}
    for r in rows:
        st_counts[stage_of(r["w"])] = st_counts.get(stage_of(r["w"]), 0) + 1
    now_counts = {}
    for r in rows:
        if not r["finished"]:                                  # commissioned customers have every stage ticked: they are counted under "Commissioned", not under Meter fix
            now_counts[r["now_key"]] = now_counts.get(r["now_key"], 0) + 1
    work_chips = ([("", "Any", len(rows)), ("none", "Not started", now_counts.get("none", 0))] + [(k, l, now_counts.get(k, 0)) for k, l in ProjectWork.STAGES]
                  + [("done", "Commissioned", sum(1 for r in rows if r["finished"]))])
    stage_chips = [("", "All", len(rows))] + [(s, s, st_counts[s]) for s in STAGES15 if st_counts.get(s)]
    ff = request.GET.get("f") if request.GET.get("f") in FILTERS else ""
    if ff:
        pick = lambda r: FILTERS[ff][1](r["w"])           # a dashboard card: look at ALL projects with this condition
    shown = [r for r in rows if (pick(r) or q) and (not ff or FILTERS[ff][1](r["w"])) and (not st_pick or stage_of(r["w"]) == st_pick) and (not stage or (r["finished"] if stage == "done" else (not r["finished"] and r["now_key"] == stage))) and (not q or q in _hay(r))]
    risk_total = sum((r["ex"]["gap"] for r in rows if r["risk"]), Decimal(0))
    if tab == "risk":
        shown.sort(key=lambda r: -r["ex"]["gap"])
    elif tab == "live":
        shown.sort(key=lambda r: (r["w"].booking_date or r["w"].commission_date or datetime.date.min, r["w"].project_id or ""), reverse=True)      # the last won project first
    elif tab in ("finished", "docs"):
        shown.sort(key=lambda r: (r["w"].commission_date or datetime.date.min), reverse=True)
    grouped, groups = (tab == "live" and not ff and not stage), []
    if grouped:                                   # the Live tab: one row per stage with its customers (the latest booking first)
        order = [s for s in STAGES15 if s not in ("Not Updated", "On Hold", "Cancelled", "Commissioned")] + ["Not Updated", "On Hold", "Cancelled", "Commissioned"]
        by_stage = {}
        for r in shown:
            by_stage.setdefault(stage_of(r["w"]), []).append(r)
        groups = [{"stage": s, "rows": by_stage[s]} for s in order if s in by_stage]
    more = (not grouped) and len(shown) > 120 and request.GET.get("all") != "1"
    return render(request, "portal/progress.html", {"grouped": grouped, "groups": groups,
        "rows": shown[:120] if more else shown, "f_label": FILTERS[ff][0] if ff else "", "f": ff, "st": st_pick, "stage_chips": stage_chips, "work_chips": work_chips, "tab_label": dict(TABS)[tab] if tab != "all" else "", "more": more, "total_shown": len(shown), "tabs": [(k, l, counts[k]) for k, l in TABS], "tab": tab, "q": q,
        "editor": editor, "director": director, "risk_total": risk_total, "red_limit": EXPOSURE_RED, "stages": ProjectWork.STAGES, "stage": stage, "feas_choices": ProjectWork.FEASIBILITY})


@require_POST
def progress_update(request, pk):
    w = get_object_or_404(ProjectWork, pk=pk)
    back = request.POST.get("next") if (request.POST.get("next") or "").startswith("/progress/") else "/progress/"
    P = request.POST
    if P.get("action") == "loan":
        if not _director(request.user):
            messages.warning(request, "Only a director can change the loan details.")
            return redirect(back)

        def _d(name):
            try:
                return datetime.date.fromisoformat((P.get(name) or "").strip())
            except ValueError:
                return None

        def _n(name, default):
            try:
                return Decimal((P.get(name) or "").replace(",", "").strip() or default)
            except Exception:
                return Decimal(default)
        w.payment_mode = "loan" if P.get("payment_mode") == "loan" else "cash"
        w.loan_amount, w.bank1_amount = _n("loan_amount", "0"), _n("bank1_amount", "140000")
        w.loan_sanctioned_on, w.bank1_received_on, w.bank2_received_on = _d("loan_sanctioned_on"), _d("bank1_received_on"), _d("bank2_received_on")
        w.updated_by, w.updated_at = request.user, timezone.now()
        w.save()
        return redirect(back + "#p%d" % w.pk)
    if not can_edit(request.user):
        messages.warning(request, "Only Fidha, Riswan and the directors can update a project.")
        return redirect(back)
    stage = P.get("stage")
    if stage in PAPER_KEYS:
        today, on = timezone.localdate(), paper_done(w, stage)
        kseb = dict(w.kseb or {})
        if stage == "kp_feas":
            w.feasibility_date, w.feasibility = (None, "") if on else (today, "ok")
        elif stage == "kp_docs":
            kseb.pop("docs", None) if on else kseb.__setitem__("docs", today.isoformat())
        elif stage == "kp_meter":
            kseb.pop("netmeter_app", None) if on else kseb.__setitem__("netmeter_app", today.isoformat())
        else:
            w.commission_date = None if on else today
        w.kseb = kseb
    elif stage in STAGE_KEYS or stage in NEW_KEYS:
        if not getattr(w, stage):
            why = gate_message(w, stage)
            if why:
                messages.warning(request, why)
                return redirect(back + "#p%d" % w.pk)
        setattr(w, stage, not getattr(w, stage))
        if stage == "testing" and w.testing:
            w.inv_program = True
        if w.testing and w.meter_fix and not w.commission_date:
            w.commission_date = timezone.localdate()
    else:
        w.work_status = (P.get("work_status") or "").strip()[:300]
        raw = (P.get("commission_date") or "").strip()
        try:
            w.commission_date = datetime.date.fromisoformat(raw) if raw else None
        except ValueError:
            pass
        w.wifi = {"yes": True, "no": False}.get(P.get("wifi"), None)
        w.handover = P.get("handover") == "on"
        if w.handover and not w.handover_date:
            w.handover_date = timezone.localdate()
        for f in ("feasibility_date", "handover_date"):
            if f in P:
                try:
                    setattr(w, f, datetime.date.fromisoformat(P[f].strip()) if P[f].strip() else None)
                except ValueError:
                    pass
        w.registration_paid = P.get("registration_paid") == "on"
        if P.get("feasibility") in ("", "ok", "issue"):
            w.feasibility = P.get("feasibility")
        w.feasibility_note = (P.get("feasibility_note") or "").strip()[:300]
    w.updated_by, w.updated_at = request.user, timezone.now()
    w.save()
    return redirect(back + "#p%d" % w.pk)


def _visible(request, w):
    user = request.user
    if can_edit(user) or _director(user):
        return True
    return bool(w.collection_id and payments.is_mine(sales.keys_of(user), w.collection.sales_name))


def _num(raw, default=0):
    try:
        return Decimal((raw or "").replace(",", "").strip() or default)
    except Exception:
        return Decimal(default)


def project_detail(request, pk):
    """One customer in full: the 12 KSEB steps with dates, serial numbers, contractor labour, invoice and warranty.  Fidha and Riswan edit."""
    from django.http import Http404
    w = get_object_or_404(ProjectWork, pk=pk)
    if not _visible(request, w):
        raise Http404
    editor = can_edit(request.user)
    if request.method == "POST":
        if not editor:
            messages.warning(request, "Only Fidha, Riswan and the directors can update a project.")
            return redirect("progress_detail", pk=w.pk)
        P = request.POST
        kseb = dict(w.kseb or {})
        for key, _l in ProjectWork.KSEB_STEPS:
            raw = (P.get("d_" + key) or "").strip()
            d = _pd(raw) if raw else None
            if key == "feasibility":
                w.feasibility_date = d
            elif key == "commissioning":
                w.commission_date = d
            elif d:
                kseb[key] = d.isoformat()
            else:
                kseb.pop(key, None)
        w.kseb = kseb
        w.registration_paid = bool(kseb.get("reg_paid")) or P.get("registration_paid") == "on"
        if kseb.get("meter_fix") and not w.meter_fix:
            w.meter_fix = True
        for f in ("name", "phone", "location", "map_link", "kw", "panel_make", "inverter_make", "sales_person", "engineer"):
            if f in P:
                setattr(w, f, (P.get(f) or "").strip()[:150])
        if "site_address" in P:
            w.site_address = (P.get("site_address") or "").strip()
        if "booking_date" in P:
            w.booking_date = _pd((P.get("booking_date") or "").strip())
        if w.name:
            w.name_key = re.sub(r"[^a-z0-9]", "", w.name.lower())
        for f in ("kseb_consumer_no", "arn", "scheme", "inverter_serial", "energy_meter_serial", "net_meter_serial", "electrical_contractor",
                  "structure_contractor", "invoice_no"):
            setattr(w, f, (P.get(f) or "").strip()[:60])
        w.panel_serials = (P.get("panel_serials") or "").strip()
        for f in ("email", "alt_phone", "pincode", "district", "region", "segment", "almm", "load_change", "system", "inverter_model", "inverter_phase", "roof_type",
                  "project_stage", "energy_meter_make", "net_meter_make", "kseb_ref", "subsidy_status", "handover_status", "handed_over_by"):
            if f in P:
                setattr(w, f, (P.get(f) or "").strip()[:100])
        if "kseb_notes" in P:
            w.kseb_notes = (P.get("kseb_notes") or "").strip()
        for f in ("panel_wp", "dc_kwp", "ac_kw"):
            if f in P:
                raw = (P.get(f) or "").strip()
                try:
                    setattr(w, f, Decimal(raw) if raw else None)
                except Exception:
                    pass
        for f in ("electrical_amount", "electrical_paid", "structure_amount", "structure_paid"):
            setattr(w, f, _num(P.get(f)))
        for f in ("panel_count", "panel_warranty_yrs", "inverter_warranty_yrs", "workmanship_yrs"):
            raw = (P.get(f) or "").strip()
            setattr(w, f, int(raw) if raw.isdigit() else None)
        for f in ("invoice_date", "handover_date"):
            setattr(w, f, _pd((P.get(f) or "").strip()) if P.get(f) else None)
        w.handover = bool(w.handover_date) or P.get("handover") == "on"
        w.updated_by, w.updated_at = request.user, timezone.now()
        w.save()
        messages.success(request, "Saved.")
        return redirect("progress_detail", pk=w.pk)
    from collections import Counter
    counter = Counter(s for o in ProjectWork.objects.exclude(panel_serials="").only("panel_serials") for s in panel_serial_list(o))
    steps, n_done, nxt = kseb_steps(w)
    today = timezone.localdate()
    return render(request, "portal/project_detail.html", {
        "w": w, "editor": editor, "steps": steps, "n_done": n_done, "next": nxt, "clocks": kseb_clocks(w, today), "warranties": warranty_list(w),
        "problems": serial_problems(w, counter), "serial_n": len(panel_serial_list(w)),
        "elec_bal": w.electrical_amount - w.electrical_paid, "struct_bal": w.structure_amount - w.structure_paid})


MASTER_COLUMNS = [
    ("Project ID", lambda w, r: w.project_id), ("Customer", lambda w, r: r["name"]), ("Phone", lambda w, r: w.phone), ("KSEB consumer no.", lambda w, r: w.kseb_consumer_no),
    ("Site address", lambda w, r: w.site_address), ("Place", lambda w, r: w.location), ("Map link", lambda w, r: w.map_link), ("Scheme", lambda w, r: w.scheme),
    ("Sales person", lambda w, r: r["owner"]), ("Site engineer", lambda w, r: w.engineer), ("kW", lambda w, r: w.kw), ("Panel", lambda w, r: w.panel_make),
    ("Inverter", lambda w, r: w.inverter_make), ("Booking date", lambda w, r: w.booking_date), ("Quotation value", lambda w, r: r["qv"]["quotation"]),
    ("Deal value", lambda w, r: r["qv"]["deal"]), ("Received", lambda w, r: r["due"]["received"] if r["due"] else None), ("Balance", lambda w, r: r["due"]["balance"] if r["due"] else None),
    ("Work now at", lambda w, r: r["now"]), ("Stages done (of 10)", lambda w, r: w.done_count), ("Material delivered %", lambda w, r: r["mat"]["pct"]), ("Work progress %", lambda w, r: r["work"]["pct"]), ("KSEB / paperwork %", lambda w, r: r["paper"]["pct"]), ("Handover documents %", lambda w, r: r["hand"]["pct"]), ("KSEB steps done (of 12)", lambda w, r: r["kseb_done"]),
    ("Feasibility date", lambda w, r: w.feasibility_date), ("Commissioning date", lambda w, r: w.commission_date), ("Handover date", lambda w, r: w.handover_date),
    ("Invoice no.", lambda w, r: w.invoice_no), ("Payment by", lambda w, r: "Bank loan" if w.is_loan else "Own money"), ("Inverter serial", lambda w, r: w.inverter_serial),
    ("Net meter serial", lambda w, r: w.net_meter_serial), ("Workmanship warranty until", lambda w, r: r["warranty"]),
    ("Email", lambda w, r: w.email), ("Alternate phone", lambda w, r: w.alt_phone), ("Pincode", lambda w, r: w.pincode), ("District", lambda w, r: w.district),
    ("Region", lambda w, r: w.region), ("Segment", lambda w, r: w.segment), ("ALMM", lambda w, r: w.almm), ("System type", lambda w, r: w.system),
    ("Load change required", lambda w, r: w.load_change), ("Panel wattage (Wp)", lambda w, r: w.panel_wp), ("No. of panels", lambda w, r: w.panel_count),
    ("DC capacity (kWp)", lambda w, r: w.dc_kwp), ("AC capacity (kW)", lambda w, r: w.ac_kw), ("Inverter model", lambda w, r: w.inverter_model),
    ("Inverter phase", lambda w, r: w.inverter_phase), ("Roof type", lambda w, r: w.roof_type), ("Energy meter make", lambda w, r: w.energy_meter_make),
    ("Energy meter serial", lambda w, r: w.energy_meter_serial), ("Net meter make", lambda w, r: w.net_meter_make), ("Panel serials", lambda w, r: w.panel_serials),
    ("Project stage", lambda w, r: w.project_stage), ("PM Surya Ghar ARN", lambda w, r: w.arn), ("KSEB ref. no.", lambda w, r: w.kseb_ref),
    ("Portal application", lambda w, r: _kd(w, "portal_app")), ("Documents to KSEB", lambda w, r: _kd(w, "docs")), ("Registration fee paid", lambda w, r: _kd(w, "reg_paid")),
    ("Work start", lambda w, r: _kd(w, "work_start")), ("Work completion", lambda w, r: _kd(w, "work_done")), ("Net meter application", lambda w, r: _kd(w, "netmeter_app")),
    ("Inspection", lambda w, r: _kd(w, "inspection")), ("Net meter fix", lambda w, r: _kd(w, "meter_fix")), ("Programming", lambda w, r: _kd(w, "programming")),
    ("Subsidy credited", lambda w, r: _kd(w, "subsidy")), ("Subsidy status", lambda w, r: w.subsidy_status),
    ("Electrical contractor", lambda w, r: w.electrical_contractor), ("Electrical amount", lambda w, r: w.electrical_amount), ("Electrical paid", lambda w, r: w.electrical_paid),
    ("Structure contractor", lambda w, r: w.structure_contractor), ("Structure amount", lambda w, r: w.structure_amount), ("Structure paid", lambda w, r: w.structure_paid),
    ("Invoice date", lambda w, r: w.invoice_date), ("Invoice value", lambda w, r: w.invoice_value), ("Handover status", lambda w, r: w.handover_status),
    ("Panel warranty (yrs)", lambda w, r: w.panel_warranty_yrs), ("Inverter warranty (yrs)", lambda w, r: w.inverter_warranty_yrs), ("Remarks", lambda w, r: w.remarks),
]


def _kd(w, key):
    from .project_dashboard import kdate
    return kdate(w, key)


def master(request):
    """The master data: one row per customer with the details, dates and money, searchable, and a CSV download (opens in Excel)."""
    import csv
    from django.http import HttpResponse
    rows = _rows_for(request)
    q = (request.GET.get("q") or "").strip().lower()
    if q:
        rows = [r for r in rows if q in " ".join(str(c(r["w"], r) or "") for _n, c in MASTER_COLUMNS).lower()]
    table = [[c(r["w"], r) for _n, c in MASTER_COLUMNS] for r in rows]
    if request.GET.get("csv"):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="dehlsen_customers_%s.csv"' % timezone.localdate().isoformat()
        resp.write("\ufeff")
        wr = csv.writer(resp)
        wr.writerow([n for n, _c in MASTER_COLUMNS])
        for row in table:
            wr.writerow(["" if v is None else v for v in row])
        return resp
    return render(request, "portal/master.html", {"cols": [n for n, _c in MASTER_COLUMNS], "table": list(zip([r["w"].pk for r in rows], table))[:400],
                                                   "total": len(table), "q": q})


def project_add(request):
    """Add a customer / project by hand (Fidha, Riswan, directors and superusers).  Everything can be completed later on the project's page."""
    if not can_edit(request.user):
        messages.warning(request, "Only Fidha, Riswan, the directors and the superusers can add a project.")
        return redirect("progress")
    prefix = "DH26-27/"
    nums = [int(m.group(1)) for m in (re.match(r"^DH26-27/(\d+)$", p or "") for p in ProjectWork.objects.values_list("project_id", flat=True)) if m]
    suggested = "%s%03d" % (prefix, (max(nums) + 1) if nums else 1)
    fields = ["name", "project_id", "phone", "alt_phone", "email", "location", "site_address", "pincode", "district", "region", "segment", "map_link", "kw",
              "panel_make", "inverter_make", "system", "almm", "scheme", "sales_person", "engineer", "payment_mode", "booking_date", "kseb_consumer_no", "load_change", "name_change"]
    values = {f: "" for f in fields}
    values["project_id"], values["payment_mode"], values["booking_date"] = suggested, "cash", timezone.localdate().isoformat()
    error = ""
    if request.method == "POST":
        values = {f: (request.POST.get(f) or "").strip() for f in fields}
        digits = re.sub(r"\D", "", values["phone"])[-10:]
        key = re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", values["name"].lower()))
        clash = None
        if values["name"]:
            for x in ProjectWork.objects.all():
                if (digits and len(digits) == 10 and re.sub(r"\D", "", x.phone or "")[-10:] == digits) or (key and x.name_key == key) or (values["project_id"] and x.project_id == values["project_id"]):
                    clash = x
                    break
        if not values["name"]:
            error = "Type the customer's name."
        elif clash and not request.POST.get("again"):
            error = "%s (%s) is already in the projects: same name, phone or project ID. Open that project instead, or tick the box below to add this one anyway." % (clash.name, clash.project_id or "no ID")
            values["_clash"] = clash.pk
        else:
            w = ProjectWork(name=values["name"][:200], name_key=key, project_id=values["project_id"][:30])
            for f in ("phone", "alt_phone", "email", "location", "pincode", "district", "region", "segment", "kw", "panel_make", "inverter_make", "system", "almm", "scheme",
                      "sales_person", "engineer", "kseb_consumer_no", "load_change", "name_change", "map_link"):
                setattr(w, f, values[f][:150] if f != "map_link" else values[f][:500])
            w.site_address = values["site_address"]
            w.payment_mode = ProjectWork.LOAN if values["payment_mode"] == "loan" else ProjectWork.CASH
            w.booking_date = _pd(values["booking_date"]) if values["booking_date"] else None
            w.project_stage = "Booked"
            w.updated_by, w.updated_at = request.user, timezone.now()
            w.save()
            messages.success(request, "%s added. Fill in the rest of the details here." % w.name)
            return redirect("progress_detail", pk=w.pk)
    return render(request, "portal/project_add.html", {"v": values, "error": error, "clash": values.get("_clash")})
