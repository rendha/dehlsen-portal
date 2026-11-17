"""Upgrade / add-on quotation screens.  Rates come from the normal rate list (Product); GST is per item (5% panel/inverter, 18% rest)."""
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_not_required  # noqa: F401  (kept for symmetry with views.py)
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from . import pdf_layout as L
from .addon_models import AddonItem, AddonQuotation, _m, default_gst
from .models import PanelOption, Product


def _unlocked(request):
    from .views import rates_unlocked
    return rates_unlocked(request)


def _dec(v, default="0"):
    try:
        return Decimal(str(v).replace(",", "").strip() or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _rate_from_gross(gross, gst, qty):
    """Per-unit rate (2 decimals, before GST) whose GST-inclusive total is closest to qty x the price the person typed."""
    base = (gross / (Decimal("1") + gst / Decimal("100"))).quantize(Decimal("0.01"))
    target, best = _m(qty * gross), None
    for d in range(-3, 4):
        r = base + Decimal(d) / 100
        t = _m(qty * r)
        err = abs(t + _m(t * gst / Decimal("100")) - target)
        if best is None or err < best[0]:
            best = (err, r)
    return best[1]


# lump-sum work lines offered in the item search; the price is typed for each job
WORK_LINES = [("Electrical Material Including Cable", "Lot"),
              ("Electrical Re cabling and Combination Re arranging", "L.S."),
              ("Structure Fabrication & Installation Work", "L.S.")]


def _can_see_all(request):
    u = request.user
    if not getattr(u, "is_authenticated", False):      # the PWA has no sign-in: everyone sees everything
        return True
    return _unlocked(request) or getattr(u, "is_staff", False) or getattr(u, "is_superuser", False)


def _mine_or_404(request, pk):
    obj = get_object_or_404(AddonQuotation, pk=pk)
    if not _can_see_all(request) and obj.created_by_id not in (None, getattr(request.user, 'id', None)):
        from django.http import Http404
        raise Http404
    return obj


def addon_products(request):
    """Type-and-search over the rate list.  The rate is sent only when the admin passkey is entered."""
    q = (request.GET.get("q") or "").strip()
    qs = Product.objects.filter(is_active=True)
    for word in q.split():
        qs = qs.filter(Q(name__icontains=word) | Q(make__icontains=word) | Q(specification__icontains=word))
    show = _unlocked(request)
    out = []
    words0 = [w.lower() for w in q.split()]
    for n, (title, unit) in enumerate(WORK_LINES):
        if words0 and all(w in title.lower() for w in words0):
            out.append({"id": "work:%d" % n, "name": title, "make": "", "unit": unit, "category": "Work / lump sum", "gst": "18",
                        "spec": "", "typed": True})
    # solar panels live in Panel options (a rate per watt), not in Products: search them too, panels first
    words = [w.lower() for w in q.split()]
    for o in PanelOption.objects.filter(is_active=True).order_by("company", "panel_type", "wattage"):
        watts = o.wattage.normalize()
        watts = int(watts) if watts == watts.to_integral_value() else watts
        name = " ".join(("%s %s %s W" % (o.company, o.panel_type, watts)).split())
        if words and not all(w in (name + " panel pv module solar").lower() for w in words):
            continue
        d = {"id": "panel:%d" % o.id, "name": name, "make": o.company, "unit": "Nos", "category": "PV Module", "gst": "5",
             "spec": "%s %s solar PV module, %s Wp" % (o.panel_type, "DCR" if o.dcr_status == "dcr" else "Non-DCR", watts)}
        if show:
            d["rate"] = str((o.rate_per_watt * o.wattage).quantize(Decimal("0.01")))
        out.append(d)
        if len(out) >= 10:
            break
    for p in qs.order_by("category", "name")[:max(15 - len(out), 5)]:
        d = {"id": p.id, "name": p.name, "make": p.make, "spec": p.specification, "unit": p.unit,
             "category": p.get_category_display(), "gst": str(default_gst(p.category))}
        if show:
            d["rate"] = str(p.rate)
        out.append(d)
    return JsonResponse({"results": out, "show_rates": show})


def addon_list(request):
    qs = AddonQuotation.objects.all()
    if not _can_see_all(request):
        qs = qs.filter(created_by=request.user)
    return render(request, "quotations/addon_list.html", {"rows": qs[:200], "show_rates": _unlocked(request)})


def addon_new(request):
    if request.method == "POST":
        P = request.POST
        name = (P.get("customer_name") or "").strip()
        descs = P.getlist("description")
        if not name or not any(d.strip() for d in descs):
            return render(request, "quotations/addon_form.html",
                          {"error": "Enter the customer name and at least one item.", "posted": P, "show_rates": _unlocked(request)})
        addon = AddonQuotation(
            customer_name=name, sales_name=(P.get("sales_name") or "").strip(),
            location=(P.get("location") or "").strip(), note=(P.get("note") or "").strip()[:300],
            validity_days=int(_dec(P.get("validity_days"), "15")) or 15,
            created_by=request.user if getattr(request.user, 'is_authenticated', False) else None)
        addon.offer_no = L.next_offer_no(AddonQuotation, timezone.localdate(), prefix="UPG")
        addon.save()
        ids, specs, makes, units = (P.getlist(k) for k in ("product_id", "specification", "make", "unit"))
        qtys, rates, gsts, modes = P.getlist("quantity"), P.getlist("rate"), P.getlist("gst"), P.getlist("rate_mode")
        for i, desc in enumerate(descs):
            desc = desc.strip()
            if not desc:
                continue
            get = lambda lst, d="": lst[i] if i < len(lst) else d
            pid = get(ids)
            product = Product.objects.filter(pk=pid).first() if pid.isdigit() else None
            panel = PanelOption.objects.filter(pk=pid[6:]).first() if pid.startswith("panel:") and pid[6:].isdigit() else None
            qty = _dec(get(qtys), "1") or Decimal("1")
            if product:   # the rate always comes from the rate list, never from the browser
                rate = product.rate
                gst = _dec(get(gsts), "") if get(gsts) else default_gst(product.category)
                make, spec, unit = get(makes) or product.make, get(specs) or product.specification, get(units) or product.unit
            elif panel:   # a solar panel from Panel options: price = watts x rate per watt, always from the server
                rate = (panel.rate_per_watt * panel.wattage).quantize(Decimal("0.01"))
                gst = _dec(get(gsts), "5") if get(gsts) else Decimal("5")
                make, spec, unit = get(makes) or panel.company, get(specs), get(units) or "Nos"
            else:         # typed item: the person types its rate
                rate, gst = _dec(get(rates)), _dec(get(gsts), "18")
                if get(modes) == "incl":      # the typed price already includes GST: work back to the rate before GST
                    rate = _rate_from_gross(rate, gst, qty)
                make, spec, unit = get(makes), get(specs), get(units) or "Nos"
            AddonItem.objects.create(addon=addon, product=product, description=desc[:300], specification=spec, make=make[:200],
                                     unit=unit[:50], quantity=qty, rate=rate, gst_percent=gst)
        addon.recalculate()
        return redirect("addon_detail", pk=addon.pk)
    return render(request, "quotations/addon_form.html", {"show_rates": _unlocked(request)})


def addon_detail(request, pk):
    addon = _mine_or_404(request, pk)
    if request.method == "POST" and "final_override" in request.POST:
        raw = request.POST.get("final_override", "").strip()
        before = addon.margin_drop
        addon.final_override = _dec(raw) if raw else None
        addon.recalculate()
        if addon.margin_drop > 0 and addon.margin_drop != before:
            _alert(addon)
        return redirect("addon_detail", pk=addon.pk)
    return render(request, "quotations/addon_detail.html", {"a": addon, "items": addon.items.all(), "show_rates": _unlocked(request), "pdf_name": _pdf_name(addon)})


def _alert(addon):
    """Tell the directors when an add-on quotation is priced below the calculated value (same idea as the normal margin alert)."""
    try:
        from django.contrib.auth import get_user_model
        from portal.notify import send_push
        title = "Low margin add-on quotation"
        body = "%s: calculated Rs %s, quoted Rs %s" % (addon.customer_name, addon.calculated_total, addon.final_total)
        for u in get_user_model().objects.filter(is_superuser=True):
            send_push(u, title, body)
    except Exception:
        pass


def _pdf_name(addon):
    return "%s_upgrade.pdf" % ("".join(c for c in addon.customer_name if c.isalnum())[:30] or "upgrade")


def addon_pdf_view(request, pk, filename):
    """The PDF inside our own page (Back and Share / Save buttons): a phone's Safari cannot open a bare PDF address reliably,
    this is how the normal quotation PDF is shown too."""
    _mine_or_404(request, pk)
    return render(request, "quotations/pdf_view.html", {"pdf_url": reverse("addon_pdf_named", args=[pk, filename]), "pdf_name": filename})


def addon_pdf(request, pk, filename=None):
    addon = _mine_or_404(request, pk)
    from .addon_pdf import build_addon_pdf
    resp = FileResponse(build_addon_pdf(addon), as_attachment=False,
                        filename=_pdf_name(addon),
                        content_type="application/pdf")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp
