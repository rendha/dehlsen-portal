"""Gets quotations from the Sales app.  The Project app and the Sales app are one website now, so the quotation views are called directly:
no internet address and no API key are needed."""
import json
from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.test import RequestFactory


class QuotationApiError(Exception):
    pass


def _get(params, path=""):
    from quotations import views as quotation_views
    import os
    view = quotation_views.materials_estimate if path.strip("/") == "estimate" else quotation_views.materials_api
    request = RequestFactory().get("/sales/api/materials/", params, HTTP_X_API_KEY=os.environ.get("MATERIALS_API_KEY", ""),
                                   HTTP_HOST="localhost")
    try:
        response = view(request)
    except Http404:
        raise QuotationApiError("The quotation was not found (or the Sales app refused the request).")
    except Exception as error:
        raise QuotationApiError("The Sales app could not answer: %s: %s" % (type(error).__name__, error))
    try:
        data = json.loads(response.content.decode("utf-8"))
    except Exception:
        raise QuotationApiError("The Sales app gave an answer that could not be read.")
    if response.status_code >= 400:
        raise QuotationApiError("The Sales app answered %s: %s" % (response.status_code, data.get("error", "")))
    return data


def search_quotations(query):
    return _get({"q": query}).get("quotations", [])


def estimate(specs):
    """The reverse of a quotation: the Sales app works out the material list (with ITS rates), the structure wage and the electrical
    work from the specifications only (panel brand / watts, inverter kW, phase, cable lengths ...)."""
    return _get({k: v for k, v in specs.items() if v not in ("", None)}, "estimate")


def get_quotation(quotation_id):
    return _get({"id": quotation_id})


def to_decimal(value, default=None):
    """'12', '12.5', '1,200' -> Decimal; anything else -> default."""
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default
    return number if number.is_finite() else default

import re as _re

_SOLAR_5 = _re.compile(r"\b(bifacial|topcon|mono ?perc|perc|solar (panel|module))\b|\b\d{3}\s*wp?\b|\binverter\b|\b\d+(\.\d+)?\s*kw\b", _re.I)


def default_gst(name, make=""):
    """GST % for an item: solar panels and solar inverters 5 %, everything else (cables, boxes, meters, earthing, BOS, structure) 18 %."""
    return Decimal("5") if _SOLAR_5.search("%s %s" % (name or "", make or "")) else Decimal("18")
