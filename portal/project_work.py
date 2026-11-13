"""Project progress: where every customer's installation stands (stage ticks), what payment that makes due, and who may update it.
Fidha and Riswan tick the stages; directors see everything; a sales person sees the projects of his own customers."""
import datetime
from decimal import Decimal
from difflib import SequenceMatcher

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import payments, sales
from .models import Collection, ProjectWork

EDITORS = {"fidha", "riswan"}                     # the only people who tick stages and update a project (user name or first name)
TABS = [("live", "Live"), ("risk", "At risk"), ("bank", "Bank pending"), ("finished", "Finished"), ("docs", "Waiting documents"), ("pay", "Payment pending"), ("feas", "Feasibility issue"), ("all", "All")]
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
    if w.collection_id and w.collection.quotation_id and w.collection.quotation_id in by_quotation:
        return by_quotation[w.collection.quotation_id]
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
    q = qmap.get(c.quotation_id) if c and c.quotation_id else None
    value, offer = None, ""
    if q is not None:
        value, offer = q["final_quotation_price"], q["offer_no"]
    elif cust is not None and cust.quoted_total:
        value, offer = cust.quoted_total, cust.offer_no
    return {"quotation": value, "offer": offer, "deal": c.net_value if c else None}


def progress(request):
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
    qids = [w.collection.quotation_id for w in works if w.collection_id and w.collection.quotation_id]
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
                     "pay": bool(d and (d["overdue"] > 0 or d["balance"] > 0)), "feas": w.feasibility == "issue",
                     "overdue": bool(d and d["overdue"] > 0), "ex": ex, "risk": bool(ex and ex["gap"] > 0 and not w.commissioned),
                     "now_key": stage_now(w)[0], "now": stage_now(w)[1], "next": stage_now(w)[2], "owner": _owner(w), "name": w.collection.customer if (w.collection_id and w.collection.customer) else w.name, "qv": qv, "bank": bank_wait, "bank_late": bank_late, "clocks": kseb_clocks(w, today), "warranty": warranty_end(w),
                     "kseb_done": kseb_steps(w)[1], "kseb_next": kseb_steps(w)[2]})
    tab = request.GET.get("tab") if request.GET.get("tab") in dict(TABS) else "live"
    q = (request.GET.get("q") or "").strip().lower()
    counts = {"risk": sum(1 for r in rows if r["risk"]), "bank": sum(1 for r in rows if r["bank"]),
              "live": sum(1 for r in rows if not r["finished"]), "finished": sum(1 for r in rows if r["finished"]), "docs": sum(1 for r in rows if r["docs"]),
              "pay": sum(1 for r in rows if r["pay"]), "feas": sum(1 for r in rows if r["feas"]), "all": len(rows)}
    pick = {"risk": lambda r: r["risk"], "bank": lambda r: r["bank"], "live": lambda r: not r["finished"], "finished": lambda r: r["finished"], "docs": lambda r: r["docs"], "pay": lambda r: r["pay"],
            "feas": lambda r: r["feas"], "all": lambda r: True}[tab]
    stage = request.GET.get("stage") if request.GET.get("stage") in set(STAGE_KEYS) | {"none"} else ""

    def _hay(r):
        return " ".join([r["w"].name, r["name"], r["w"].location or "", r["w"].phone or "", _owner(r["w"]), r["now"], _ALIASES.get(r["now_key"], "")]).lower()
    shown = [r for r in rows if pick(r) and (not stage or r["now_key"] == stage) and (not q or q in _hay(r))]
    risk_total = sum((r["ex"]["gap"] for r in rows if r["risk"]), Decimal(0))
    if tab == "risk":
        shown.sort(key=lambda r: -r["ex"]["gap"])
    elif tab == "live":
        shown.sort(key=lambda r: (-r["w"].progress, r["w"].name.lower()))
    elif tab in ("finished", "docs"):
        shown.sort(key=lambda r: (r["w"].commission_date or datetime.date.min), reverse=True)
    more = len(shown) > 120 and request.GET.get("all") != "1"
    return render(request, "portal/progress.html", {
        "rows": shown[:120] if more else shown, "more": more, "total_shown": len(shown), "tabs": [(k, l, counts[k]) for k, l in TABS], "tab": tab, "q": q,
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
    if stage in STAGE_KEYS:
        if not getattr(w, stage):
            why = gate_message(w, stage)
            if why:
                messages.warning(request, why)
                return redirect(back + "#p%d" % w.pk)
        setattr(w, stage, not getattr(w, stage))
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
        for f in ("kseb_consumer_no", "arn", "scheme", "inverter_serial", "energy_meter_serial", "net_meter_serial", "electrical_contractor",
                  "structure_contractor", "invoice_no"):
            setattr(w, f, (P.get(f) or "").strip()[:60])
        w.panel_serials = (P.get("panel_serials") or "").strip()
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
