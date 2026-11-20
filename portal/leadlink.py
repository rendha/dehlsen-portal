"""Link an existing (old) quotation to a lead, and make a lead from a quotation that has none.  Nothing here changes the lead's stage by itself."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import sales
from .models import Lead
from .views import _digits, _is_lead_head, _lead_log, _may_touch


def _quotations():
    from quotations.models import Quotation
    return Quotation


def _rows(qs, linked):
    """Shows each quotation with its number, date, customer, size and price, and whether a lead already has it."""
    out = []
    for q in qs:
        out.append({"id": q.id, "offer": q.offer_no or ("#%s" % q.id), "name": q.customer_name or q.business_name, "phone": q.phone, "date": q.date,
                    "kw": q.system_size, "price": sales.indian(q.final_quotation_price) if q.final_quotation_price else "", "won": q.is_customer,
                    "lead": linked.get(q.id)})
    return out


def _linked_map():
    """quotation id -> the lead that already holds it."""
    return {l.quotation_id: l for l in Lead.objects.exclude(quotation_id__isnull=True)}


@login_required
def link(request, pk):
    """Pick an old quotation for this lead.  Same-phone ones come first."""
    lead = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, lead):
        messages.error(request, "Only the lead's owner or a lead head can link a quotation.")
        return redirect("leads")
    Quotation = _quotations()
    q = (request.GET.get("q") or "").strip()
    linked = _linked_map()
    qs = Quotation.objects.all()
    if q:
        d = _digits(q)
        flt = Q(customer_name__icontains=q) | Q(business_name__icontains=q) | Q(offer_no__icontains=q)
        if len(d) >= 4:
            flt |= Q(phone__icontains=d[-10:])
        qs = qs.filter(flt)
    mine = _digits(lead.phone)
    rows = _rows(qs.order_by("-date", "-id")[:60], linked)
    for r in rows:
        r["same"] = bool(mine and _digits(r["phone"]) == mine)
    rows.sort(key=lambda r: (not r["same"], 0))          # same phone first, the date order is kept
    current = Quotation.objects.filter(pk=lead.quotation_id).first() if lead.quotation_id else None
    return render(request, "portal/lead_link.html", {"lead": lead, "rows": rows, "q": q, "current": current, "mode": "link"})


@login_required
@require_POST
def link_save(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, lead):
        messages.error(request, "Only the lead's owner or a lead head can link a quotation.")
        return redirect("leads")
    Quotation = _quotations()
    qid = request.POST.get("quotation", "")
    quote = Quotation.objects.filter(pk=qid).first() if qid.isdigit() else None
    if quote is None:
        messages.error(request, "That quotation was not found.")
        return redirect(reverse("lead_link", args=[lead.pk]))
    other = Lead.objects.filter(quotation_id=quote.pk).exclude(pk=lead.pk).first()
    if other is not None:
        messages.error(request, "That quotation already belongs to the lead of %s." % other.customer_name)
        return redirect(reverse("lead_link", args=[lead.pk]))
    lead.quotation_id = quote.pk
    lead.save(update_fields=["quotation_id"])
    _lead_log(lead, request.user, "quote", "linked quotation %s" % (quote.offer_no or quote.pk), alert=False)
    messages.success(request, "Quotation %s linked to %s." % (quote.offer_no or quote.pk, lead.customer_name))
    return redirect("leads")


@login_required
@require_POST
def unlink(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if not _may_touch(request.user, lead):
        messages.error(request, "Only the lead's owner or a lead head can do this.")
        return redirect("leads")
    old = lead.quotation_id
    lead.quotation_id = None
    lead.save(update_fields=["quotation_id"])
    _lead_log(lead, request.user, "note", "unlinked quotation #%s" % old, alert=False)
    messages.success(request, "Quotation unlinked.")
    return redirect("leads")


@login_required
def unlinked(request):
    """Quotations that no lead holds (by link or by phone).  Make a lead from any of them."""
    Quotation = _quotations()
    linked = set(_linked_map())
    phones = {_digits(l.phone) for l in Lead.objects.all() if _digits(l.phone)}
    q = (request.GET.get("q") or "").strip()
    qs = Quotation.objects.all()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(business_name__icontains=q) | Q(offer_no__icontains=q) | Q(phone__icontains=_digits(q) or "@@"))
    rows = [r for r in _rows(qs.order_by("-date", "-id")[:400], {}) if r["id"] not in linked and _digits(r["phone"]) not in phones]
    return render(request, "portal/lead_link.html", {"rows": rows[:80], "q": q, "mode": "unlinked", "total": len(rows)})


@login_required
@require_POST
def from_quotation(request, qid):
    """Makes a lead from an old quotation: name and phone are copied, the lead belongs to the person pressing the button, the stage is not touched."""
    Quotation = _quotations()
    quote = get_object_or_404(Quotation, pk=qid)
    if Lead.objects.filter(quotation_id=quote.pk).exists():
        messages.error(request, "A lead already holds this quotation.")
        return redirect("lead_unlinked")
    lead = Lead.objects.create(customer_name=(quote.customer_name or quote.business_name or "Customer")[:120], phone=(quote.phone or "")[:30],
                               area=(quote.location or "")[:100], need=Lead.CALL, entered_by=request.user, assigned_to=request.user,
                               quotation_id=quote.pk, next_step="Follow up", note="Made from the old quotation %s" % (quote.offer_no or quote.pk))
    _lead_log(lead, request.user, "quote", "made this lead from quotation %s" % (quote.offer_no or quote.pk), alert=False)
    messages.success(request, "Lead made for %s." % lead.customer_name)
    return redirect("lead_unlinked")
