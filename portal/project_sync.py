"""Every customer the quotation app confirms gets a project here automatically (so the master data fills itself).
Called when a quotation is confirmed (quotations/views.py, portal/views.py), by the daily job, and by  manage.py sync_projects.
A customer who is already in the list (same quotation, same payment row, same phone or the same name) is never added twice: it is only linked."""
import re
from difflib import SequenceMatcher

from .models import ProjectWork


# test quotations that must never become a project (the "kkj" and "dj" ones made for testing).  Add an offer number here to ignore another.
IGNORED_OFFERS = {"INQ-20261104060734448911", "INQ-20261110111029181011"}


def _compact(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", (s or "").lower()))


def _last10(s):
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def _same(a, b):
    a, b = _compact(a), _compact(b)
    return bool(a) and bool(b) and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.9)


def ensure_projects(quotation_ids=None, dry=False, say=None):
    """Make a project for every confirmed customer that has none.  Returns (created, linked)."""
    from quotations.models import Quotation
    from . import payments
    qs = Quotation.objects.filter(is_customer=True).exclude(offer_no__in=IGNORED_OFFERS)
    if quotation_ids is not None:
        qs = qs.filter(id__in=quotation_ids)
    works = list(ProjectWork.objects.select_related("collection"))
    by_q = {w.quotation_id: w for w in works if w.quotation_id}
    by_col = {w.collection_id: w for w in works if w.collection_id}
    created = linked = 0
    for q in qs.order_by("date"):
        if q.id in by_q:
            continue
        try:
            col = payments._find(q)
        except Exception:
            col = None
        w = by_col.get(col.pk) if col else None
        if w is None:
            w = next((x for x in works if x.collection_id and x.collection.quotation_id == q.id), None)
        if w is None and _last10(q.phone):
            w = next((x for x in works if _last10(x.phone) == _last10(q.phone)), None)
        if w is None:
            names = [q.business_name, q.customer_name]
            w = next((x for x in works if any(_same(x.name, n) or (x.collection_id and _same(x.collection.customer, n)) for n in names if n)), None)
        if w is not None:
            linked += 1
            if say:
                say("   link   %s  ->  %s" % (q.business_name or q.customer_name, w.name))
        else:
            created += 1
            name = (col.customer if col and col.customer else (q.business_name or q.customer_name)) or "Customer %s" % q.offer_no
            if say:
                say("   NEW    %s  (%s)" % (name, q.offer_no))
            w = ProjectWork(name=name[:200], name_key=_compact(name), collection=col, project_id=col.project_id if col else "")
            works.append(w)
        if dry:
            continue
        w.quotation_id = q.id
        if col and not w.collection_id:
            w.collection, w.project_id = col, col.project_id
        for f, v in (("phone", q.phone), ("site_address", q.address), ("location", q.location), ("sales_person", q.customer_name),
                     ("kw", ("%g" % q.system_size) if q.system_size else ""), ("system", q.system_type or "")):
            if v and not getattr(w, f):
                setattr(w, f, str(v)[:150] if f == "location" else str(v))
        if q.date and not w.booking_date:
            w.booking_date = q.date
        w.save()
        by_q[q.id] = w
        if w.collection_id:
            by_col[w.collection_id] = w
    return created, linked
