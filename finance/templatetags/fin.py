from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def inr(value):
    """12345678 -> 1,23,45,678 (Indian grouping, no decimals when whole, otherwise 2)."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    neg = d < 0
    d = abs(d)
    whole = int(d)
    frac = d - whole
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    if frac:
        s += ("%.2f" % frac)[1:]
    return ("-" if neg else "") + s


@register.filter
def label(status):
    return {"paid": "Paid", "overdue": "Overdue", "soon": "Due soon", "part": "Part paid", "open": "Not due"}.get(status, status)


@register.filter
def tagclass(status):
    return {"paid": "g", "overdue": "r", "soon": "a", "part": "", "open": ""}.get(status, "")
