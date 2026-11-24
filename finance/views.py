"""Accounts: vendor proformas, invoices, payments, payables.  Read: Boss, Store, Accounts, Project.  Write: Accounts (and superusers); Store may add proformas.
Approving a proforma: Boss / superuser only."""
import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from store.views import is_accounts, is_boss, is_project, is_store

from .forms import InvoiceForm, PaymentForm, ProformaForm, VendorForm
from .models import ZERO, Attachment, Invoice, Payment, Proforma, Vendor


def can_view(u):
    from portal import views as pv                       # directors see all of Accounts too
    return is_boss(u) or is_store(u) or is_accounts(u) or is_project(u) or bool(pv._is_director(u))


def can_edit(u):
    return is_accounts(u)


def can_add_proforma(u):
    return is_accounts(u) or is_store(u)


def can_approve(u):
    return is_boss(u)


def _deny(msg="Only the Boss, Store, Accounts and Project people see the vendor accounts."):
    return HttpResponseForbidden(msg)


def _invoices():
    return Invoice.objects.select_related("vendor", "proforma").prefetch_related("payments", "proforma__payments", "proforma__invoices")


def _unchecked():
    """Customer payments Accounts has not yet ticked against the bank statement."""
    try:
        from portal.models import Payment as CustomerPayment
        return CustomerPayment.objects.filter(bank_checked=False, confirmed=True).count()
    except Exception:
        return 0


def _pending_receipts():
    """Customer payments typed by sales people that Accounts has not confirmed yet."""
    try:
        from portal.models import Payment as CustomerPayment
        return CustomerPayment.objects.filter(confirmed=False).count()
    except Exception:
        return 0


def _ctx(request, tab, **kw):
    kw.update({"tab": tab, "edit": can_edit(request.user), "can_add_pf": can_add_proforma(request.user), "approver": can_approve(request.user),
               "n_confirm": Invoice.objects.exclude(check_note="").count() + Proforma.objects.exclude(check_note="").count()
               + Payment.objects.exclude(check_note="").count(),
               "n_wait": Proforma.objects.filter(status=Proforma.PENDING).count(), "n_receipts": _pending_receipts(), "n_unchecked": _unchecked()})
    return kw


# ---------------------------------------------------------------- payables
@login_required
def payables(request):
    if not can_view(request.user):
        return _deny()
    company, vendor_id, status = request.GET.get("company", ""), request.GET.get("vendor", ""), request.GET.get("status", "unpaid")
    rows = []
    for inv in _invoices():
        if company and inv.company != company:
            continue
        if vendor_id and str(inv.vendor_id) != vendor_id:
            continue
        st = inv.status
        if status == "unpaid" and st == "paid":
            continue
        if status in ("overdue", "soon", "paid") and st != status:
            continue
        rows.append(inv)
    rows.sort(key=lambda i: (i.status == "paid", i.due_date, i.id))
    unpaid = [i for i in _invoices() if i.balance > 0 and (not company or i.company == company)]
    total = sum((i.balance for i in unpaid), ZERO)
    overdue = sum((i.balance for i in unpaid if i.status == "overdue"), ZERO)
    soon = sum((i.balance for i in unpaid if i.status == "soon"), ZERO)
    adv = sum((p.advance_paid for p in Proforma.objects.exclude(status=Proforma.INVOICED).prefetch_related("payments")), ZERO)
    return render(request, "finance/payables.html", _ctx(
        request, "payables", rows=rows, total=total, overdue=overdue, soon=soon, advances=adv, company=company, vendor_id=vendor_id, status=status,
        vendors=Vendor.objects.all(), shown=sum((i.balance for i in rows if i.balance > 0), ZERO)))


@login_required
def export_payables(request):
    if not can_view(request.user):
        return _deny()
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="payables.csv"'
    w = csv.writer(resp)
    w.writerow(["Vendor", "Invoice no.", "Invoice date", "Due date", "Company", "Delivery to", "Customer / site", "Description", "Amount", "Paid", "Advance applied", "Balance", "Status"])
    for i in _invoices():
        if i.balance > 0:
            w.writerow([i.vendor.name, i.number, i.date, i.due_date, i.company, i.delivery_to, i.customer_name, i.description, i.amount, i.paid, i.advance_applied, i.balance, i.status])
    return resp


# ---------------------------------------------------------------- proformas
@login_required
def proformas(request):
    if not can_view(request.user):
        return _deny()
    status = request.GET.get("status", "open")
    qs = Proforma.objects.select_related("vendor").prefetch_related("payments", "invoices")
    if status == "open":
        qs = qs.filter(status__in=[Proforma.PENDING, Proforma.APPROVED])
    elif status != "all":
        qs = qs.filter(status=status)
    return render(request, "finance/proformas.html", _ctx(request, "proformas", rows=list(qs), status=status, statuses=Proforma.STATUSES))


@login_required
def proforma_detail(request, pk):
    if not can_view(request.user):
        return _deny()
    pf = get_object_or_404(Proforma.objects.select_related("vendor"), pk=pk)
    return render(request, "finance/proforma.html", _ctx(request, "proformas", pf=pf, payments=pf.payments.all(), form=PaymentForm(), invoice=pf.invoice,
                                                                   att=Attachment.objects.filter(proforma=pf).only("id", "name").first()))


@login_required
def proforma_new(request):
    if not can_add_proforma(request.user):
        return _deny("Only Accounts and Store add proformas.")
    form = ProformaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        pf = form.save(commit=False)
        pf.created_by = request.user
        pf.save()
        form.save_file(pf)
        messages.success(request, "Proforma saved. It waits for approval and is not counted as owed.")
        return redirect("fin_proforma", pk=pf.pk)
    return render(request, "finance/form.html", _ctx(request, "proformas", form=form, title="New proforma (a vendor's request for money)",
                                                      note="A proforma is only a request. It is not counted in Payables until the vendor's invoice is entered."))


@login_required
def proforma_edit(request, pk):
    if not can_edit(request.user):
        return _deny("Only Accounts edit proformas.")
    pf = get_object_or_404(Proforma, pk=pk)
    form = ProformaForm(request.POST or None, request.FILES or None, instance=pf)
    if request.method == "POST" and form.is_valid():
        form.save()
        form.save_file(pf)
        return redirect("fin_proforma", pk=pf.pk)
    return render(request, "finance/form.html", _ctx(request, "proformas", form=form, title="Edit proforma"))


@login_required
@require_POST
def proforma_status(request, pk):
    pf = get_object_or_404(Proforma, pk=pk)
    new = request.POST.get("status")
    if new in (Proforma.APPROVED, Proforma.REJECTED):
        if not can_approve(request.user):
            return _deny("Only the Boss approves or rejects a proforma.")
    elif new == Proforma.CANCELLED:
        if not can_edit(request.user):
            return _deny()
    else:
        return redirect("fin_proforma", pk=pk)
    pf.status, pf.status_note = new, request.POST.get("note", "")[:300]
    pf.save(update_fields=["status", "status_note"])
    return redirect("fin_proforma", pk=pk)


@login_required
def advances(request):
    if not can_view(request.user):
        return _deny()
    rows = [p for p in Proforma.objects.select_related("vendor").prefetch_related("payments").exclude(status=Proforma.INVOICED) if p.advance_paid > 0]
    return render(request, "finance/advances.html", _ctx(request, "advances", rows=rows, total=sum((p.advance_paid for p in rows), ZERO)))


# ---------------------------------------------------------------- invoices
@login_required
def invoice_new(request):
    if not can_edit(request.user):
        return _deny("Only Accounts enter vendor invoices.")
    initial = {}
    pf = None
    if request.GET.get("proforma", "").isdigit():
        pf = Proforma.objects.filter(pk=request.GET["proforma"]).select_related("vendor").first()
    if pf:
        initial = {"vendor": pf.vendor_id, "proforma": pf.pk, "company": pf.company, "delivery_to": pf.delivery_to, "customer_name": pf.customer_name,
                   "description": pf.description, "amount": pf.amount, "credit_days": pf.vendor.credit_days, "date": timezone.localdate()}
    form = InvoiceForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        inv = form.save(commit=False)
        inv.created_by = request.user
        inv.save()
        form.save_file(inv)
        if inv.proforma_id:
            Proforma.objects.filter(pk=inv.proforma_id).update(status=Proforma.INVOICED)
        messages.success(request, "Invoice saved.%s" % (" The advance paid on its proforma is deducted." if inv.proforma_id and inv.advance_applied else ""))
        return redirect("fin_invoice", pk=inv.pk)
    return render(request, "finance/form.html", _ctx(request, "payables", form=form, title="New vendor invoice", credit_map=_credit_map(),
                                                      note="Credit days are counted from the invoice date. Only invoices are counted as owed."))


@login_required
def invoice_edit(request, pk):
    if not can_edit(request.user):
        return _deny()
    inv = get_object_or_404(Invoice, pk=pk)
    form = InvoiceForm(request.POST or None, request.FILES or None, instance=inv)
    if request.method == "POST" and form.is_valid():
        inv = form.save()
        form.save_file(inv)
        if inv.proforma_id:
            Proforma.objects.filter(pk=inv.proforma_id).update(status=Proforma.INVOICED)
        return redirect("fin_invoice", pk=pk)
    return render(request, "finance/form.html", _ctx(request, "payables", form=form, title="Edit invoice", credit_map=_credit_map()))


def _credit_map():
    return {str(v.pk): v.credit_days for v in Vendor.objects.all()}


@login_required
def invoice_detail(request, pk):
    if not can_view(request.user):
        return _deny()
    inv = get_object_or_404(_invoices(), pk=pk)
    return render(request, "finance/invoice.html", _ctx(request, "payables", inv=inv, payments=inv.payments.all(), form=PaymentForm(initial={"amount": inv.balance if inv.balance > 0 else ""}),
                                                                   att=Attachment.objects.filter(invoice=inv).only("id", "name").first()))


@login_required
@require_POST
def invoice_flag(request, pk):
    if not can_edit(request.user):
        return _deny()
    inv = get_object_or_404(Invoice, pk=pk)
    what = request.POST.get("what")
    if what == "approve":
        inv.approved = not inv.approved
    elif what == "received":
        inv.material_received = not inv.material_received
        inv.received_on = timezone.localdate() if inv.material_received else None
    inv.save()
    return redirect("fin_invoice", pk=pk)


# ---------------------------------------------------------------- payments
@login_required
@require_POST
def payment_add(request, kind, pk):
    if not can_edit(request.user):
        return _deny("Only Accounts record payments.")
    target = get_object_or_404(Invoice if kind == "invoice" else Proforma, pk=pk)
    form = PaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Payment not saved: " + "; ".join("%s: %s" % (k, " ".join(v)) for k, v in form.errors.items()))
    else:
        p = form.save(commit=False)
        p.vendor, p.created_by = target.vendor, request.user
        if kind == "invoice":
            p.invoice = target
        else:
            p.proforma = target
        p.save()
        messages.success(request, "Payment recorded.")
    return redirect("fin_invoice" if kind == "invoice" else "fin_proforma", pk=pk)


@login_required
@require_POST
def payment_delete(request, pk):
    if not request.user.is_superuser:
        return _deny("Only a director / superuser deletes a recorded payment.")
    p = get_object_or_404(Payment, pk=pk)
    back = ("fin_invoice", p.invoice_id) if p.invoice_id else ("fin_proforma", p.proforma_id)
    p.delete()
    return redirect(back[0], pk=back[1])


# ---------------------------------------------------------------- vendors
@login_required
def vendors(request):
    if not can_view(request.user):
        return _deny()
    invs = list(_invoices())
    rows = []
    for v in Vendor.objects.all():
        mine = [i for i in invs if i.vendor_id == v.id]
        owed = sum((i.balance for i in mine if i.balance > 0), ZERO)
        adv = sum((p.advance_paid for p in v.proformas.exclude(status=Proforma.INVOICED).prefetch_related("payments")), ZERO)
        rows.append({"v": v, "n": len(mine), "total": sum((i.amount for i in mine), ZERO), "owed": owed, "adv": adv})
    rows.sort(key=lambda r: -r["owed"])
    return render(request, "finance/vendors.html", _ctx(request, "vendors", rows=rows))


@login_required
def vendor_edit(request, pk=None):
    if not can_edit(request.user):
        return _deny("Only Accounts edit vendors.")
    v = get_object_or_404(Vendor, pk=pk) if pk else None
    form = VendorForm(request.POST or None, instance=v)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("fin_vendors")
    return render(request, "finance/form.html", _ctx(request, "vendors", form=form, title="Vendor" if v else "New vendor"))


# ---------------------------------------------------------------- to confirm
@login_required
def to_confirm(request):
    if not can_view(request.user):
        return _deny()
    return render(request, "finance/confirm.html", _ctx(
        request, "confirm", invoices=Invoice.objects.exclude(check_note="").select_related("vendor"),
        proformas=Proforma.objects.exclude(check_note="").select_related("vendor"), payments=Payment.objects.exclude(check_note="").select_related("vendor", "invoice", "proforma")))


@login_required
@require_POST
def confirm_clear(request, kind, pk):
    if not can_edit(request.user):
        return _deny()
    model = {"invoice": Invoice, "proforma": Proforma, "payment": Payment}.get(kind)
    if model:
        model.objects.filter(pk=pk).update(check_note="")
    return redirect("fin_confirm")


@login_required
def attachment_file(request, pk):
    """Open an uploaded proforma / invoice file."""
    if not can_view(request.user):
        return _deny()
    a = get_object_or_404(Attachment, pk=pk)
    resp = HttpResponse(bytes(a.data), content_type=a.content_type)
    resp["Content-Disposition"] = 'inline; filename="%s"' % "".join(c for c in a.name if c.isalnum() or c in " ._-")[:100]
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "sandbox"
    return resp
