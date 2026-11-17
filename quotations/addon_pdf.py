"""PDF of an add-on quotation, in the normal quotation design: cover, welcome page, then ONE summary page with the items table
(a separate BOQ page only when there are too many items for the box)."""
import io

from pypdf import PdfReader, PdfWriter

from . import pdf_layout as L
from .pdf_generator import ASSETS_DIR, ASSETS_URI, PAYMENT_NOTE, PAYMENT_TERMS, _part, bank_details

BOX_ITEMS = 5      # items that fit in the overview box; more than this -> the BOQ page carries the item-wise prices

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
         "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_1000(n):
    out = []
    if n >= 100:
        out.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        out.append(_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))
    elif n:
        out.append(_ONES[n])
    return " ".join(out)


def amount_in_words(value):
    """215800 -> 'Rupees Two Lakh Fifteen Thousand Eight Hundred Only' (Indian system, paise when present)."""
    from decimal import Decimal, ROUND_HALF_UP
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees, paise = int(d), int((d - int(d)) * 100)
    parts = []
    for div, name in ((10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")):
        if rupees >= div:
            parts.append(_below_1000(rupees // div) + " " + name)
            rupees %= div
    if rupees:
        parts.append(_below_1000(rupees))
    text = "Rupees " + (" ".join(parts) or "Zero")
    if paise:
        text += " and " + _below_1000(paise) + " Paise"
    return text + " Only"


def scope_text(a):
    """Scope of Work (and the 'existing inverter retained' line) worded from the items on the quotation."""
    names = " ".join((it.description or "").lower() for it in a.items.all())
    has = lambda *w: any(x in names for x in w)
    parts = []
    if has("module", "panel", "pv ", "solar pv"):
        parts.append("solar modules")
    if has("structure", "fabricat", "mounting"):
        parts.append("structure fabrication")
    if has("inverter"):
        parts.append("inverter")
    if has("cable", "cabling", "wire", "electrical", "connector", "combiner", "dcdb", "acdb"):
        parts.append("cabling, connectors and electrical works")
    if has("earth", "lightning"):
        parts.append("earthing and lightning protection")
    if parts:
        what = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
        scope = ("Supply of %s, installation, testing and commissioning required for upgrading the existing solar plant." % what)
    else:
        scope = "Supply, installation, testing and commissioning of the items listed above for the existing solar plant."
    keep = "" if has("inverter") else "The existing inverter will be retained and utilized for the upgraded solar plant."
    return scope, keep


def _qty_text(it):
    unit = (it.unit or "").strip()
    if unit.lower().replace(".", "").replace(" ", "") in ("ls", "lumpsum"):
        return "L.S."
    return ("%s %s" % (L.fmt_num(it.quantity), unit)).strip()


def _cover(a):
    rows = [
        ("OFFER NO: %s" % a.offer_no, 53.4, 676.8, 12, 155),
        ("CATEGORY: UPGRADE", 225.9, 676.8, 12, 160),
        ("LOCATION: %s" % (a.location or "-").upper(), 401.6, 676.8, 12, 145),
        ("ITEMS: %d NOS" % a.items.count(), 54.1, 716.2, 12, 155),
        ("DATED: %s" % a.created_at.strftime("%d-%m-%Y"), 226.7, 716.2, 12, 160),
        ("QUOTATION VALIDITY: %s DAYS" % a.validity_days, 401.6, 716.0, 10, 145),
        ("BUSINESS NAME: %s" % a.customer_name.upper(), 54.5, 755.5, 12, 490),
    ]
    return [{"text": t, "left": L.pt(l), "top": L.pt(tp), "size": L.pt(L.fit_size(t, b, w))} for t, l, tp, b, w in rows]


def _rate_with_gst(it):
    from decimal import Decimal, ROUND_HALF_UP
    return (it.rate * (Decimal("1") + it.gst_percent / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rows(a):
    out = []
    for n, it in enumerate(a.items.all(), 1):
        out.append({"sr": n, "particular": it.description, "spec": L.text_html(it.specification) if it.specification else "",
                    "qty": _qty_text(it), "make": it.make,
                    # customer-facing: rate and amount INCLUDE GST
                    "rate": L.money_text(_rate_with_gst(it)), "amount": L.money_text(it.total_value)})
    return out


def build_addon_pdf(a):
    rows = _rows(a)
    overflow = len(rows) > BOX_ITEMS
    base = {"assets": ASSETS_URI}
    parts = [_part("cover.html", dict(base, cover_fields=_cover(a))), PdfReader(str(ASSETS_DIR / "page_welcome.pdf"))]
    diff = a.final_total - a.calculated_total      # lines add up to the calculated total; show any manual price change
    adjust = ""
    if diff != 0:
        adjust = ("- " if diff < 0 else "") + L.money_text(abs(diff))
    price = dict(adjust=adjust, adjust_label="Special price adjustment" if diff < 0 else "Adjustment",
                 total_plain=L.money_text(a.final_total), words=amount_in_words(a.final_total), note=a.note,
                 total="₹ %s/-" % L.money_text(a.final_total))
    scope, keep = scope_text(a)
    price.update(scope=scope, keep=keep)
    if True:      # BOQ & Price page: full details (specification, make, rate, amount), scope of work and notes
        parts.append(_part("addon_boq.html", dict(base, boq_rows=rows, **price)))
    parts.append(_part("addon_summary.html", dict(
        base, rows=[] if overflow else rows, overflow=overflow, **price,
        payment_terms=PAYMENT_TERMS, payment_note=PAYMENT_NOTE,
        bank_lines=L.positioned([{"text": "%s: %s" % (k, v)} for k, v in bank_details()], L.BANK_TOP, L.BANK_PITCH))))
    w = PdfWriter()
    for part in parts:
        for page in part.pages:
            w.add_page(page)
    w.add_metadata({"/Title": "Upgrade quotation %s" % a.offer_no, "/Author": "Dehlsen Energy"})
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf
