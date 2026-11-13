"""The numbers of the home dashboard (directors / lead heads): lead -> quotation -> confirmed -> project -> service.
Every block is calculated on its own and returns None if its tables are not ready, so one problem never breaks the home page."""
import datetime
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from . import sales


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def period_dates(kind, today):
    if kind == "year":
        start = datetime.date(today.year if today.month >= 4 else today.year - 1, 4, 1)      # financial year, April to March
        return start, today, "This year"
    if kind == "quarter":
        first = ((today.month - 1) // 3) * 3 + 1
        return datetime.date(today.year, first, 1), today, "This quarter"
    return today.replace(day=1), today, "This month"


def _clients(qs):
    from quotations import dashboard_stats as stats
    return {stats.name_key(n) for n in qs.values_list("customer_name", flat=True) if n}


def _pct(a, b):
    return int(round(a * 100 / b)) if b else 0


def _lakh(v):
    return sales.short(v)


def build(kind="month", today=None):
    today = today or timezone.localdate()
    start, end, title = period_dates(kind, today)
    data = {"title": title, "kind": kind, "start": start}

    # 1 leads, 2 quotations, 3 confirmed, 4 projects, 5 service
    def journey():
        from quotations.models import Quotation
        from .models import Lead
        leads = Lead.objects.filter(created_at__date__gte=start, created_at__date__lte=end).count()
        quoted = len(_clients(Quotation.objects.filter(date__gte=start, date__lte=end)))
        confirmed = len(_clients(Quotation.objects.filter(is_customer=True, date__gte=start, date__lte=end)))
        from store.models import Customer
        running = Customer.objects.exclude(status=Customer.DONE).count()
        service = _safe(lambda: _service_count(start, end), 0) or 0
        return [
            {"n": leads, "label": "new enquiries", "step": "Leads", "pct": None, "color": "#3B73B9"},
            {"n": quoted, "label": "quotes sent", "step": "Quotations", "pct": _pct(quoted, leads) if leads else None, "color": "#3B73B9"},
            {"n": confirmed, "label": "became customers", "step": "Confirmed", "pct": _pct(confirmed, quoted) if quoted else None, "color": "#2e9e5b"},
            {"n": running, "label": "projects running now", "step": "Project", "pct": None, "color": "#E8730C"},
            {"n": service, "label": "cleaning and service visits", "step": "Service", "pct": None, "color": "#7b4fd1"},
        ]
    data["journey"] = _safe(journey)

    # needs attention
    def attention():
        from quotations.models import Quotation
        from store.models import Customer, Payment
        from .models import Lead
        rows = []
        # quotations with no reply for 7 days (not confirmed, 7 to 60 days old; one per client)
        old = Quotation.objects.filter(is_customer=False, date__lte=today - datetime.timedelta(days=7), date__gte=today - datetime.timedelta(days=60))
        confirmed = _clients(Quotation.objects.filter(is_customer=True))
        from quotations import dashboard_stats as stats
        waiting = {stats.name_key(n) for n in old.values_list("customer_name", flat=True) if n} - confirmed
        rows.append({"n": len(waiting), "title": "Quotations with no reply for 7 days", "sub": "Quotations · call these customers again", "url": "/sales/"})
        stale = Lead.objects.filter(done=False, created_at__lt=timezone.now() - datetime.timedelta(days=7)).count()
        rows.append({"n": stale, "title": "Leads with no follow-up for 7 days", "sub": "Leads · still open", "url": reverse("leads") + "?stale=1"})
        nolist = Customer.objects.exclude(status=Customer.DONE).filter(lines__isnull=True).distinct().count()
        rows.append({"n": nolist, "title": "Confirmed customers with no material list", "sub": "Project · the store cannot start packing", "url": "/project/"})
        try:
            from quotations import low_margin
            cut = low_margin.rows(limit=200)
            if cut:
                rows.append({"n": len(cut), "title": "Quotations given below the calculated price", "sub": "Quotations · margin decreased (admin passkey page)", "url": reverse("low_margin")})
        except Exception:
            pass
        owing, balance = 0, Decimal(0)
        for c in Customer.objects.all():
            paid = c.payments.aggregate(t=Sum("amount"))["t"] or Decimal(0)
            left = c.total_due - paid
            if c.total_due > 0 and left > 0:
                owing += 1
                balance += left
        rows.append({"n": owing, "title": "Projects with money still to collect", "sub": "Project · ₹%s balance in total" % _lakh(balance), "url": "/project/"})
        wait = _safe(_waiting_for_date)
        if wait is not None:
            rows.append({"n": wait[0], "title": "Customers waiting for a service date", "sub": "Service · %d cleaning, %d general services" % (wait[1], wait[2]), "url": "/service/"})
        part = _safe(_partly_done)
        if part is not None:
            rows.append({"n": part, "title": "Jobs marked partially done", "sub": "Service · the rest of the work needs a new date", "url": "/service/"})
        return rows
    data["attention"] = _safe(attention)

    # sales target of the quarter
    def target():
        lines, company = sales.build(today)
        q = lines["quarter"]
        if not q:
            return None
        places = [l for l in q if l["is_place"]] or q
        total = company["quarter"]
        return {"got": total["got_short"], "target": total["target_short"], "percent": total["percent"], "bar": total["bar"],
                "time_percent": q[0]["time_percent"], "days_left": q[0]["days_left"],
                "places": [{"name": l["name"], "percent": l["percent"], "bar": l["bar"],
                            "who": ", ".join(m["name"].split(" ")[0] for m in l.get("members", []))} for l in places]}
    data["target"] = _safe(target)

    def projects():
        from store.models import Customer
        draft = Customer.objects.filter(status=Customer.DRAFT).count()
        sent = Customer.objects.filter(status=Customer.SENT).count()
        done = Customer.objects.filter(status=Customer.DONE).count()
        total = draft + sent + done
        return {"total": total, "rows": [("Material list being made", draft), ("Store is packing / with the store", sent), ("Completed", done)]}
    data["projects"] = _safe(projects)

    def money():
        from store.models import Customer, Payment
        agreed = sum((c.total_due for c in Customer.objects.all()), Decimal(0))
        received = Payment.objects.aggregate(t=Sum("amount"))["t"] or Decimal(0)
        return {"agreed": _lakh(agreed), "received": _lakh(received), "left": _lakh(max(agreed - received, Decimal(0))),
                "percent": min(_pct(received, agreed), 100)}
    data["money"] = _safe(money)

    data["service"] = _safe(lambda: _service_block(start, end, today))
    return data


def _service_count(start, end):
    from cleaning.models import CleaningSchedule
    return CleaningSchedule.objects.filter(scheduled_date__gte=start, scheduled_date__lte=end, status="Completed").count()


def _service_block(start, end, today):
    from cleaning.models import CleaningSchedule
    base = CleaningSchedule.objects.filter(scheduled_date__gte=start, scheduled_date__lte=end)
    done = base.filter(status="Completed").count()
    part = base.filter(status="Partially done").count()
    booked = CleaningSchedule.objects.filter(scheduled_date__gt=today, status="Scheduled").count()
    total = max(done + part + booked, 1)
    block = {"done": done, "part": part, "booked": booked, "w_done": _pct(done, total), "w_part": _pct(part, total), "w_booked": _pct(booked, total)}
    try:
        block["free"] = base.filter(is_free=True).count()
        block["paid"] = base.filter(is_free=False).count()
    except Exception:
        block["free"] = block["paid"] = None
    return block


def _partly_done():
    from cleaning.models import CleaningSchedule
    return CleaningSchedule.objects.filter(status="Partially done").count()


def _waiting_for_date():
    from cleaning import models as cm
    model = getattr(cm, "ScheduleRequest", None) or getattr(cm, "SchedulerRequest")
    pending = model.objects.filter(status__in=["Pending", "pending"]) if hasattr(model, "status") else model.objects.all()
    cleaning = sum(1 for r in pending if str(getattr(r, "kind", "cleaning")).lower().startswith("clean"))
    return len(pending), cleaning, len(pending) - cleaning
