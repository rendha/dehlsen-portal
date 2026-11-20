"""The Customers module: what each customer paid and still owes.  Anybody can note a payment received from a customer; it waits as "pending"
until Accounts, a director or Fousan confirms it (then it counts as received everywhere: collections, receivables, targets of money, dashboards).
A payment typed by one of those confirmers counts at once.  The first payment of a customer is the "Advance", the next ones Payment 1, Payment 2 ..."""
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import payments, sales
from .models import Collection, Payment
from .views import _can_confirm_money

ZERO = Decimal(0)


def _inr(v):
    return sales.indian(v or 0)


def _row(c, pending):
    net, got = Decimal(c.net_value or 0), Decimal(c.received or 0)
    return {"c": c, "net": _inr(net), "got": _inr(got), "left": _inr(max(net - got, ZERO)), "left_n": max(net - got, ZERO), "nodeal": net <= 0,
            "pct": int(min(100, got * 100 / net)) if net > 0 else 0, "pending": len(pending), "pending_sum": _inr(sum((p.amount for p in pending), ZERO))}


@login_required
def home(request):
    q = (request.GET.get("q") or "").strip()
    show = request.GET.get("show") or ("all" if q else "owing")          # opens on the customers who still owe money; a search looks at everybody
    confirmer = _can_confirm_money(request.user)
    pend_all = list(Payment.objects.filter(confirmed=False).select_related("collection", "entered_by").order_by("date", "id"))
    by_c = {}
    for p in pend_all:
        by_c.setdefault(p.collection_id, []).append(p)
    cols = Collection.objects.all()
    if q:
        cols = cols.filter(Q(customer__icontains=q) | Q(project_id__icontains=q) | Q(sales_name__icontains=q) | Q(region__icontains=q))
    rows = [_row(c, by_c.get(c.pk, [])) for c in cols.order_by("customer")]
    if show == "owing":
        rows = [r for r in rows if r["left_n"] > 0 or r["nodeal"]]
        rows.sort(key=lambda r: -r["left_n"])
    elif show == "pending":
        rows = [r for r in rows if r["pending"]]
    allc = list(Collection.objects.all())
    sold = sum((Decimal(c.net_value or 0) for c in allc), ZERO)
    got = sum((Decimal(c.received or 0) for c in allc), ZERO)
    waiting = []
    if confirmer:
        for p in pend_all:
            waiting.append({"p": p, "amount": _inr(p.amount), "by": (p.entered_by.get_full_name() or p.entered_by.get_username()) if p.entered_by else "", "c": p.collection})
    ctx = {"rows": rows[:400], "more": max(len(rows) - 400, 0), "q": q, "show": show, "confirmer": confirmer, "waiting": waiting,
           "n": len(allc), "sold": _inr(sold), "got": _inr(got), "left": _inr(max(sold - got, ZERO)),
           "pend_n": len(pend_all), "pend_sum": _inr(sum((p.amount for p in pend_all), ZERO)), "next": request.get_full_path()}
    return render(request, "portal/customers.html", ctx)


@login_required
def detail(request, pk):
    c = get_object_or_404(Collection, pk=pk)
    confirmer = _can_confirm_money(request.user)
    pays = sorted(c.payments.select_related("entered_by", "confirmed_by"), key=lambda x: (x.date or datetime.date.min, x.id))
    labels = payments.pay_labels(pays)
    run, out = ZERO, []
    net = Decimal(c.net_value or 0)
    for x in pays:
        if x.confirmed:
            run += x.amount
        out.append({"p": x, "label": labels.get(x.id, ""), "amount": _inr(x.amount), "run": _inr(run), "left": _inr(max(net - run, ZERO)),
                    "by": (x.entered_by.get_full_name() or x.entered_by.get_username()) if x.entered_by else ("sheet" if x.from_sheet else "")})
    pend = [p for p in pays if not p.confirmed]
    got = Decimal(c.received or 0)
    ctx = {"c": c, "pays": out, "confirmer": confirmer, "today": timezone.localdate().isoformat(), "net": _inr(net), "got": _inr(got), "left": _inr(max(net - got, ZERO)),
           "nodeal": net <= 0, "pct": int(min(100, got * 100 / net)) if net > 0 else 0, "pend_n": len(pend), "pend_sum": _inr(sum((p.amount for p in pend), ZERO)),
           "first": not pays}
    return render(request, "portal/customer.html", ctx)


@login_required
@require_POST
def pay(request, pk):
    c = get_object_or_404(Collection, pk=pk)
    try:
        amount = Decimal((request.POST.get("amount") or "").replace(",", "").strip())
        date = datetime.date.fromisoformat(request.POST.get("date") or timezone.localdate().isoformat())
    except (InvalidOperation, ValueError):
        amount, date = None, None
    if not amount or amount <= 0 or date > timezone.localdate():
        messages.error(request, "Enter the amount, and a date that is not in the future.")
        return redirect("cust_detail", pk=pk)
    auto = _can_confirm_money(request.user)
    stage = "advance" if not c.payments.exists() else "other"
    new_pay = Payment.objects.create(collection=c, amount=amount, date=date, stage=stage, note=(request.POST.get("note") or "")[:200], entered_by=request.user,
                                     confirmed=auto, confirmed_by=request.user if auto else None, confirmed_on=timezone.localdate() if auto else None)
    payments.tell_accounts(new_pay, request.user)
    if auto:
        Collection.objects.filter(pk=c.pk).update(received=F("received") + amount)
        messages.success(request, "Payment of Rs %s recorded for %s." % (amount, c.customer))
    else:
        messages.success(request, "Payment of Rs %s noted for %s. It counts as received once Accounts confirms it." % (amount, c.customer))
    return redirect("cust_detail", pk=pk)


def _back(request, pk):
    nxt = request.POST.get("next") or ""
    return redirect(nxt) if nxt.startswith("/") and not nxt.startswith("//") else redirect("cust_detail", pk=pk)


@login_required
@require_POST
def confirm(request, pk):
    if not _can_confirm_money(request.user):
        return HttpResponseForbidden("Only Accounts, the directors and Fousan confirm a customer payment.")
    pay_ = get_object_or_404(Payment, pk=pk)
    if not pay_.confirmed:
        updated = Payment.objects.filter(pk=pay_.pk, confirmed=False).update(confirmed=True, confirmed_by=request.user, confirmed_on=timezone.localdate())
        if updated:
            Collection.objects.filter(pk=pay_.collection_id).update(received=F("received") + pay_.amount)
            messages.success(request, "Payment of Rs %s confirmed. It now counts as received." % pay_.amount)
    return _back(request, pay_.collection_id)


@login_required
@require_POST
def reject(request, pk):
    if not _can_confirm_money(request.user):
        return HttpResponseForbidden("Only Accounts, the directors and Fousan handle a customer payment.")
    pay_ = get_object_or_404(Payment, pk=pk)
    cid = pay_.collection_id
    if not pay_.confirmed:
        pay_.delete()
        messages.success(request, "The unconfirmed payment was removed (not received).")
    return _back(request, cid)
