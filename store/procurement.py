"""Procurement: what we buy from suppliers (credit or paid, due dates), and for each customer: quotation, money received, material dispatched, balance.
Read: Boss, Store, Accounts, Project.  Write: Store and Accounts (the Boss only looks)."""
import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Customer, Line, Payment, Purchase, Supplier, SupplierPayment
from .views import _money, is_accounts, is_boss, is_project, is_store

ZERO = Decimal("0")


def can_view(u):
    return is_boss(u) or is_store(u) or is_accounts(u) or is_project(u)


def can_edit(u):
    return is_store(u) or is_accounts(u)


def _date(s, default=None):
    try:
        return datetime.date.fromisoformat((s or "").strip())
    except ValueError:
        return default


def _deny():
    return HttpResponseForbidden("Only the Boss, Store, Accounts and Project people see procurement.")


def _lines(customer):
    return [l for l in customer.lines.all() if l.quantity > 0]


def customer_position(customer):
    """One customer: quotation value, money received, material dispatched (at cost, store marked Done), balance and supplier side."""
    lines = _lines(customer)
    material = sum((l.amount for l in lines), ZERO)
    sent = sum((l.amount for l in lines if l.store_status == Line.DONE), ZERO)
    paid = sum((p.amount for p in customer.payments.all()), ZERO)
    quote = customer.total_due
    purchases = list(customer.purchases.all())
    return {
        "c": customer, "quote": quote, "paid": paid, "balance": (quote - paid) if quote > 0 else None,
        "material": material, "sent": sent, "to_send": material - sent,
        "n_lines": len(lines), "n_done": sum(1 for l in lines if l.store_status == Line.DONE),
        "diff": paid - sent,                                                     # money received minus material dispatched (negative = we gave more than was paid)
        "tied": sent - paid if sent > paid else ZERO,                           # material given beyond the money received
        "bought": sum((p.amount for p in purchases), ZERO), "owed": sum((p.balance for p in purchases), ZERO),
        "paid_pct": int(min(100, paid * 100 / quote)) if quote > 0 else 0,
        "sent_pct": int(min(100, sent * 100 / material)) if material > 0 else 0,
    }


def upcoming(today):
    """Everything that is coming up: bills to pay, deliveries awaited, material still to buy, sites the crew visits soon."""
    purchases = list(Purchase.objects.select_related("supplier", "customer").prefetch_related("payments"))
    dues = []
    for p in purchases:
        bal = p.balance
        if bal > 0:
            p.days = (p.due_date - today).days if p.due_date else None
            dues.append(p)
    dues.sort(key=lambda p: (p.due_date is None, p.due_date or today))
    overdue = [p for p in dues if p.days is not None and p.days < 0]
    week = [p for p in dues if p.days is not None and 0 <= p.days <= 7]
    waiting = [p for p in purchases if p.received_on is None]
    for p in waiting:
        p.late = bool(p.expected_on and p.expected_on < today)
    waiting.sort(key=lambda p: (p.expected_on is None, p.expected_on or today))

    to_buy = []
    for c in Customer.objects.exclude(status=Customer.DONE).prefetch_related("lines", "purchases"):
        items = [l for l in _lines(c) if l.source == Line.PURCHASE and l.store_status != Line.DONE]
        if items:
            to_buy.append({"c": c, "n": len(items), "value": sum((l.amount for l in items), ZERO),
                           "ordered": sum((p.amount for p in c.purchases.all()), ZERO)})
    to_buy.sort(key=lambda r: r["value"], reverse=True)

    crew = []
    try:
        from portal.models import CrewAssignment
        visits = CrewAssignment.objects.filter(date__range=(today, today + datetime.timedelta(days=7))).exclude(status="cancelled").select_related("project")
        seen = set()
        for v in visits:
            if not v.project_id or v.project_id in seen:
                continue
            seen.add(v.project_id)
            pr = v.project
            cust = None
            if getattr(pr, "quotation_id", None):
                cust = Customer.objects.filter(quotation_id=pr.quotation_id).first()
            if cust is None:
                cust = Customer.objects.filter(name__iexact=pr.name).first()
            row = {"date": v.date, "team": v.team, "work": v.work, "name": pr.name, "customer": cust}
            if cust is not None:
                ls = _lines(cust)
                row.update(n=len(ls), done=sum(1 for l in ls if l.store_status == Line.DONE))
                row["ok"] = bool(ls) and row["done"] == row["n"]
            crew.append(row)
    except Exception:
        pass
    return {"purchases": purchases, "dues": dues, "overdue": overdue, "week": week, "waiting": waiting, "to_buy": to_buy, "crew": crew}


@login_required
def proc_home(request):
    if not can_view(request.user):
        return _deny()
    today = timezone.localdate()
    up = upcoming(today)
    owed_by = {}
    for p in up["purchases"]:
        r = owed_by.setdefault(p.supplier_id, {"s": p.supplier, "n": 0, "total": ZERO, "owed": ZERO, "next": None})
        r["n"] += 1
        r["total"] += p.amount
        if p.balance > 0:
            r["owed"] += p.balance
            if p.due_date and (r["next"] is None or p.due_date < r["next"]):
                r["next"] = p.due_date
    suppliers = sorted(owed_by.values(), key=lambda r: r["owed"], reverse=True)
    ctx = {
        "up": up, "today": today, "editor": can_edit(request.user), "suppliers": suppliers,
        "owed_total": sum((p.balance for p in up["dues"]), ZERO),
        "overdue_total": sum((p.balance for p in up["overdue"]), ZERO), "week_total": sum((p.balance for p in up["week"]), ZERO),
        "to_buy_total": sum((r["value"] for r in up["to_buy"]), ZERO), "recent": up["purchases"][:15],
        "crew_short": [r for r in up["crew"] if not r.get("ok")],
    }
    return render(request, "store/proc_home.html", ctx)


@login_required
def proc_customers(request):
    if not can_view(request.user):
        return _deny()
    q = request.GET.get("q", "").strip().lower()
    f = request.GET.get("f", "")
    rows = []
    for c in Customer.objects.prefetch_related("lines", "payments", "purchases__payments"):
        if q and not all(w in " ".join([c.name, c.person, c.offer_no, c.phone, c.location]).lower() for w in q.split()):
            continue
        r = customer_position(c)
        if f == "tied" and not r["tied"]:
            continue
        if f == "due" and not (r["balance"] and r["balance"] > 0):
            continue
        if f == "owed" and not r["owed"]:
            continue
        if f == "tosend" and not r["to_send"]:
            continue
        rows.append(r)
    if f == "tied":
        rows.sort(key=lambda r: r["tied"], reverse=True)
    elif f == "due":
        rows.sort(key=lambda r: r["balance"], reverse=True)
    elif f == "owed":
        rows.sort(key=lambda r: r["owed"], reverse=True)
    tot = {k: sum((r[k] for r in rows if r[k]), ZERO) for k in ("quote", "paid", "balance", "material", "sent", "diff", "tied", "bought", "owed")}
    return render(request, "store/proc_customers.html", {"rows": rows, "tot": tot, "q": request.GET.get("q", ""), "f": f})


@login_required
def proc_customer(request, pk):
    if not can_view(request.user):
        return _deny()
    c = get_object_or_404(Customer.objects.prefetch_related("lines", "payments", "purchases__payments", "purchases__supplier"), pk=pk)
    r = customer_position(c)
    lines = _lines(c)
    return render(request, "store/proc_customer.html", {
        "r": r, "c": c, "sent_lines": [l for l in lines if l.store_status == Line.DONE],
        "open_lines": [l for l in lines if l.store_status != Line.DONE], "payments": list(c.payments.all()),
        "purchases": list(c.purchases.all()), "today": timezone.localdate(), "editor": can_edit(request.user)})


@login_required
def proc_add(request):
    if not can_view(request.user):
        return _deny()
    if not can_edit(request.user):
        return HttpResponseForbidden("Only the Store and Accounts people add purchases.")
    today = timezone.localdate()
    customers = list(Customer.objects.order_by("name"))
    labels = {"%s - %s" % (c.name, c.offer_no) if c.offer_no else c.name: c for c in customers}
    v = {"ordered_on": today.isoformat(), "pay": "paid"}
    if request.GET.get("customer"):
        c0 = Customer.objects.filter(pk=request.GET["customer"]).first()
        if c0:
            v["customer"] = "%s - %s" % (c0.name, c0.offer_no) if c0.offer_no else c0.name
    error = ""
    if request.method == "POST":
        v = request.POST.dict()
        sup_name = (v.get("supplier_other", "").strip() if v.get("supplier") == "__new__" else v.get("supplier", "").strip())
        amount = _money(v.get("amount"))
        ordered_on = _date(v.get("ordered_on"), today)
        cust_txt = v.get("customer", "").strip()
        cust = labels.get(cust_txt)
        if cust is None and cust_txt:
            hits = [c for c in customers if cust_txt.lower() in c.name.lower()]
            cust = hits[0] if len(hits) == 1 else None
            if cust is None:
                error = "Choose the customer from the list, or leave it empty for general stock."
        if not sup_name:
            error = "Choose the supplier (or add a new one)."
        elif amount is None:
            error = "Type the bill amount (a number above zero)."
        elif not v.get("description", "").strip():
            error = "Write what was bought."
        if not error:
            sup, _ = Supplier.objects.get_or_create(name=sup_name[:150])
            credit = v.get("pay") == "credit"
            p = Purchase.objects.create(
                supplier=sup, customer=cust, description=v["description"].strip()[:300], invoice_no=v.get("invoice_no", "").strip()[:60],
                ordered_on=ordered_on, amount=amount, credit=credit, due_date=_date(v.get("due_date")) if credit else None,
                expected_on=_date(v.get("expected_on")), received_on=_date(v.get("received_on")), note=v.get("note", "").strip()[:250],
                created_by=request.user.get_username()[:150])
            if not credit:
                SupplierPayment.objects.create(purchase=p, amount=amount, paid_on=ordered_on, mode=v.get("mode") if v.get("mode") in dict(Payment.MODES) else Payment.BANK,
                                               recorded_by=request.user.get_username()[:150])
            messages.success(request, "Purchase saved: %s, ₹%s%s." % (sup.name, amount, " on credit" if credit else " paid"))
            return redirect("proc_purchase", pk=p.pk)
    return render(request, "store/proc_add.html", {
        "v": v, "error": error, "suppliers": list(Supplier.objects.values_list("name", flat=True)), "labels": list(labels.keys()),
        "modes": Payment.MODES})


@login_required
def proc_purchase(request, pk):
    if not can_view(request.user):
        return _deny()
    p = get_object_or_404(Purchase.objects.select_related("supplier", "customer").prefetch_related("payments"), pk=pk)
    editor = can_edit(request.user)
    if request.method == "POST":
        if not editor:
            return HttpResponseForbidden("Only the Store and Accounts people change purchases.")
        a = request.POST.get("action")
        who = request.user.get_username()[:150]
        if a == "pay":
            amt = _money(request.POST.get("amount"))
            if amt is None:
                messages.error(request, "Type the amount paid.")
            else:
                SupplierPayment.objects.create(purchase=p, amount=amt, paid_on=_date(request.POST.get("paid_on"), timezone.localdate()),
                                               mode=request.POST.get("mode") if request.POST.get("mode") in dict(Payment.MODES) else Payment.BANK,
                                               note=request.POST.get("note", "").strip()[:200], recorded_by=who)
                messages.success(request, "Payment of ₹%s saved." % amt)
        elif a == "del_pay":
            SupplierPayment.objects.filter(pk=request.POST.get("pay_id"), purchase=p).delete()
            messages.success(request, "Payment removed.")
        elif a == "dates":
            p.credit = request.POST.get("credit") == "1"
            p.due_date = _date(request.POST.get("due_date"))
            p.expected_on = _date(request.POST.get("expected_on"))
            p.received_on = _date(request.POST.get("received_on"))
            p.invoice_no = request.POST.get("invoice_no", "").strip()[:60]
            p.note = request.POST.get("note", "").strip()[:250]
            p.save()
            messages.success(request, "Saved.")
        elif a == "received":
            p.received_on = timezone.localdate()
            p.save(update_fields=["received_on"])
            messages.success(request, "Marked as received today.")
        elif a == "delete":
            p.delete()
            messages.success(request, "Purchase deleted.")
            return redirect("proc_home")
        return redirect("proc_purchase", pk=p.pk)
    return render(request, "store/proc_purchase.html", {"p": p, "editor": editor, "payments": list(p.payments.all()), "modes": Payment.MODES,
                                                          "today": timezone.localdate()})
