"""Accounts: what customers still owe us (receivables) and the confirmation of customer payments.
Data = portal.Collection (sold value, received) and portal.Payment.  A payment typed by a sales person is PENDING until Accounts confirms it with the
bank; only then does it count in the received total.  Accounts / a director enter payments that count at once."""
import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import views as fin
from .models import ZERO

SLOW_DAYS = 30


def _portal():
    from portal import views as pv
    from portal.models import Collection, Payment
    return pv, Collection, Payment


def can_see(u):
    pv, _, _ = _portal()
    return bool(fin.can_view(u) or pv._is_director(u))


def limited(u):
    """True = no vendor side (payables, proformas, vendors): only people allowed in the vendor accounts see those tabs."""
    return not fin.can_view(u)


def own_only(u):
    """A sales person who cannot confirm money: sees only the receivables of his own customers."""
    return not (can_see(u) or can_confirm(u))


def _mine(u, collection):
    from portal import payments
    from portal import sales
    return payments.is_mine(sales.keys_of(u), collection.sales_name)


def can_see_profit(u):
    """Margins are shown to the Boss, directors and Accounts only."""
    return bool(fin.can_approve(u) or can_confirm(u))


def can_confirm(u):
    pv, _, _ = _portal()
    return pv._can_confirm_money(u)


def _row(c):
    pays = list(c.payments.all())
    ok = [p for p in pays if p.confirmed]
    last = max((p.date for p in ok if p.date), default=None)
    today = timezone.localdate()
    ref = last or c.booking_date
    pending = [p for p in pays if not p.confirmed]
    gp = c.expected_gp or ZERO
    share = (c.received / c.net_value) if c.net_value > 0 else ZERO
    return {"gp": gp, "gp_got": (gp * min(share, 1)).quantize(Decimal("1")), "gp_left": (gp - gp * min(share, 1)).quantize(Decimal("1")),
            "c": c, "balance": max(c.net_value - c.received, ZERO), "nodeal": c.net_value <= 0, "last": last, "days": (today - ref).days if ref else None,
            "pending": pending, "pending_sum": sum((p.amount for p in pending), ZERO),
            "pct": int(min(100, c.received * 100 / c.net_value)) if c.net_value > 0 else 0}


@login_required
def receivables(request):
    _, Collection, _ = _portal()
    lim = own_only(request.user)
    region, person, show = request.GET.get("region", ""), request.GET.get("person", ""), request.GET.get("show", "open")
    all_rows = [_row(c) for c in Collection.objects.prefetch_related("payments") if not lim or _mine(request.user, c)]
    regions = sorted({r["c"].region for r in all_rows if r["c"].region})
    people = sorted({r["c"].sales_name for r in all_rows if r["c"].sales_name})
    rows = [r for r in all_rows if (r["balance"] > 0 or r["nodeal"]) and (not region or r["c"].region == region) and (not person or r["c"].sales_name == person)]
    if show == "slow":
        rows = [r for r in rows if r["days"] is not None and r["days"] >= SLOW_DAYS]
    elif show == "pending":
        rows = [r for r in rows if r["pending"]]
    rows.sort(key=lambda r: -r["balance"])
    base = [r for r in all_rows if r["balance"] > 0]
    ctx = fin._ctx(request, "receivables", rows=rows, region=region, person=person, show=show, regions=regions, people=people,
                   to_collect=sum((r["balance"] for r in base), ZERO), sold=sum((r["c"].net_value for r in base), ZERO),
                   collected=sum((r["c"].received for r in base), ZERO), n_open=len(base),
                   pending_sum=sum((r["pending_sum"] for r in all_rows), ZERO), pending_n=sum(len(r["pending"]) for r in all_rows),
                   slow_sum=sum((r["balance"] for r in base if r["days"] is not None and r["days"] >= SLOW_DAYS), ZERO), shown=sum((r["balance"] for r in rows), ZERO),
                   slow_days=SLOW_DAYS, profit=can_see_profit(request.user), limited=limited(request.user),
                   gp_total=sum((r["gp"] for r in base), ZERO), gp_left=sum((r["gp_left"] for r in base), ZERO),
                   gp_n=sum(1 for r in base if r["gp"] > 0), gp_missing=sum(1 for r in base if not r["gp"]))
    return render(request, "finance/receivables.html", ctx)


@login_required
def receivable(request, pk):
    _, Collection, _ = _portal()
    c = get_object_or_404(Collection.objects.prefetch_related("payments__entered_by", "payments__confirmed_by"), pk=pk)
    lim = own_only(request.user)
    if lim and not _mine(request.user, c):
        return HttpResponseForbidden("You see the receivables of your own customers only.")
    from portal.models import Payment
    pays = sorted(c.payments.all(), key=lambda x: (x.date or datetime.date.min, x.id))
    from portal.payments import pay_labels
    labels = pay_labels(pays)
    run = ZERO
    for x in pays:                                   # money received so far after this payment (only confirmed ones count)
        if x.confirmed:
            run += x.amount
        x.running = run
        x.label = labels.get(x.id, "")
        x.left = c.net_value - run
    return render(request, "finance/receivable.html", fin._ctx(request, "receivables", r=_row(c), c=c, payments=pays, stages=Payment.STAGES,
                                                               today=timezone.localdate().isoformat(), confirmer=can_confirm(request.user), profit=can_see_profit(request.user), limited=limited(request.user)))


@login_required
@require_POST
def receipt_confirm(request, pk):
    _, _, Payment = _portal()
    if not can_confirm(request.user):
        return HttpResponseForbidden("Only Accounts confirms a customer payment.")
    pay = get_object_or_404(Payment, pk=pk)
    if not pay.confirmed:
        from portal.models import Collection
        Payment.objects.filter(pk=pay.pk, confirmed=False).update(confirmed=True, confirmed_by=request.user, confirmed_on=timezone.localdate())
        Collection.objects.filter(pk=pay.collection_id).update(received=F("received") + pay.amount)
        messages.success(request, "Payment of Rs %s confirmed. It now counts as received." % pay.amount)
    return redirect("fin_receivable", pk=pay.collection_id)


@login_required
@require_POST
def receipt_reject(request, pk):
    _, _, Payment = _portal()
    if not can_confirm(request.user):
        return HttpResponseForbidden("Only Accounts handles a customer payment.")
    pay = get_object_or_404(Payment, pk=pk)
    cid = pay.collection_id
    if not pay.confirmed:
        pay.delete()
        messages.success(request, "The unconfirmed payment was removed (not received).")
    return redirect("fin_receivable", pk=cid)


@login_required
def received(request):
    """Every customer payment entered lately, whoever entered it, so Accounts can match each with the bank statement."""
    if not (can_see(request.user) or can_confirm(request.user)):
        return HttpResponseForbidden("Only Accounts, the directors and Fousan see this list.")
    _, _, Payment = _portal()
    show = request.GET.get("show", "open")
    qs = Payment.objects.select_related("collection", "entered_by", "bank_checked_by").filter(confirmed=True, from_sheet=False,
                                                                                                created_at__gte=timezone.now() - datetime.timedelta(days=45))
    if show == "open":
        qs = qs.filter(bank_checked=False)
    rows = list(qs.order_by("-created_at")[:200])
    from portal.payments import pay_labels
    for p in rows:
        p.label = pay_labels(list(p.collection.payments.all())).get(p.id, "")
    return render(request, "finance/received.html", fin._ctx(request, "received", rows=rows, show=show, confirmer=can_confirm(request.user),
                                                              limited=limited(request.user), total=sum((p.amount for p in rows), ZERO)))


@login_required
@require_POST
def received_tick(request, pk):
    _, _, Payment = _portal()
    if not can_confirm(request.user):
        return HttpResponseForbidden("Only Accounts, the directors and Fousan can tick a payment against the bank.")
    undo = bool(request.POST.get("undo"))
    Payment.objects.filter(pk=pk).update(bank_checked=not undo, bank_checked_by=None if undo else request.user,
                                         bank_checked_on=None if undo else timezone.localdate())
    return redirect(request.POST.get("next") or "fin_received")
