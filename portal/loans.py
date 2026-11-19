"""Bank-loan customers who are waiting for the bank: they are NOT projects yet.
Sanctioned -> the lead is marked Won (the project is made) and the loan details go to the project.
Rejected   -> switch to own money / another bank, or the lead is marked Lost.
Shown on the project dashboard; daily reminders go to the person following the loan (Anupama by default)."""
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import BankLoan, Lead, Task, TaskType

OWNER_NAMES = ("anupama",)      # follows the bank
SLOW_DAYS = 30                  # a loan waiting longer than this is flagged


def _owner_default():
    q = Q()
    for n in OWNER_NAMES:
        q |= Q(username__iexact=n) | Q(first_name__iexact=n)
    return get_user_model().objects.filter(q, is_active=True).first()


def _is_director(user):
    p = getattr(user, "portal_profile", None)
    return bool(user.is_superuser or (p and p.director))


def may_edit(user, lead, loan=None):
    from .views import _may_touch
    return bool(_may_touch(user, lead) or _is_director(user) or (loan and loan.owner_id == user.id)
                or (user.get_username() or "").lower() in OWNER_NAMES or (user.first_name or "").lower() in OWNER_NAMES)


def _date(v):
    try:
        return datetime.date.fromisoformat((v or "").strip())
    except ValueError:
        return None


def _amount(v):
    try:
        return max(Decimal(str(v or "0").replace(",", "").strip() or "0"), 0)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _log(lead, user, text):
    from .views import _lead_log
    _lead_log(lead, user, "note", text)


def _sanction(request, lead, loan):
    """Mark the lead Won (if it is not yet a customer) and copy the loan into the project."""
    from quotations.models import Quotation
    from .views import _attach_stages, _make_won
    from .models import ProjectWork
    _attach_stages([lead])
    if not lead.quote:
        messages.warning(request, "Make the quotation for this customer first, then mark the loan sanctioned.")
        return False
    q = Quotation.objects.get(pk=lead.quote["id"])
    if not q.is_customer:
        _make_won(request, lead)
        q.refresh_from_db()
        if not q.is_customer:
            return False
    w = ProjectWork.objects.filter(quotation_id=q.id).first()
    if w:
        w.payment_mode, w.loan_amount = ProjectWork.LOAN, loan.amount
        w.loan_sanctioned_on = loan.sanctioned_on
        w.save(update_fields=["payment_mode", "loan_amount", "loan_sanctioned_on"])
    return True


def detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    loan = BankLoan.objects.filter(lead=lead).first()
    if not may_edit(request.user, lead, loan):
        return redirect("leads")
    if request.method == "POST":
        act = request.POST.get("action", "save")
        if loan is None:
            loan = BankLoan(lead=lead, owner=_owner_default())
        if act == "save" or act in ("apply", "query", "sanctioned", "reject"):
            loan.bank = request.POST.get("bank", loan.bank).strip()[:100]
            loan.branch = request.POST.get("branch", loan.branch).strip()[:100]
            if "amount" in request.POST:
                loan.amount = _amount(request.POST.get("amount"))
            if "applied_on" in request.POST:
                loan.applied_on = _date(request.POST.get("applied_on"))
            if "expected_on" in request.POST:
                loan.expected_on = _date(request.POST.get("expected_on"))
            if "notes" in request.POST:
                loan.notes = request.POST.get("notes", "").strip()[:3000]
            oid = request.POST.get("owner", "")
            if oid.isdigit():
                loan.owner = get_user_model().objects.filter(pk=int(oid), is_active=True).first() or loan.owner
        loan.updated_at = timezone.now()
        if act == "apply":
            loan.status, loan.applied_on = BankLoan.APPLIED, loan.applied_on or timezone.localdate()
            _log(lead, request.user, "bank loan: applied to %s" % (loan.bank or "the bank"))
        elif act == "query":
            loan.status = BankLoan.QUERY
            _log(lead, request.user, "bank loan: query from the bank")
        elif act == "docs":
            loan.status = BankLoan.DOCS
        elif act == "sanctioned":
            loan.sanctioned_on = _date(request.POST.get("sanctioned_on")) or timezone.localdate()
            loan.save()
            if _sanction(request, lead, loan):
                loan.status = BankLoan.SANCTIONED
                loan.save()
                _log(lead, request.user, "bank loan SANCTIONED (Rs %s)" % int(loan.amount))
                messages.success(request, "Loan sanctioned. %s is now a project." % lead.customer_name)
                return redirect("project_dashboard")
            return redirect("loan_detail", pk=lead.pk)
        elif act == "reject":
            loan.status = BankLoan.REJECTED
            loan.reject_reason = request.POST.get("reject_reason", "").strip()[:200]
            _log(lead, request.user, "bank loan REJECTED" + (": " + loan.reject_reason if loan.reject_reason else ""))
        elif act == "cash":
            loan.status = BankLoan.CASH
            _log(lead, request.user, "bank loan dropped - the customer will pay with own money")
            loan.save()
            messages.success(request, "Switched to own money. Mark the lead Won when the customer confirms.")
            return redirect("leads")
        elif act == "retry":
            loan.status, loan.applied_on, loan.reject_reason = BankLoan.APPLIED, timezone.localdate(), ""
            _log(lead, request.user, "bank loan: applied again to %s" % (loan.bank or "another bank"))
        elif act == "lost":
            loan.status = BankLoan.LOST
            lead.lost, lead.done, lead.lost_reason = True, True, "Loan rejected"
            lead.save(update_fields=["lost", "done", "lost_reason"])
            _log(lead, request.user, "marked the lead LOST - bank loan rejected")
            loan.save()
            messages.success(request, "Lead marked Lost (loan rejected).")
            return redirect("leads")
        loan.save()
        if act == "save":
            messages.success(request, "Loan details saved.")
        return redirect("loan_detail", pk=lead.pk)
    if loan is None:
        loan = BankLoan(lead=lead, owner=_owner_default())
    people = get_user_model().objects.filter(is_active=True).order_by("first_name", "username")
    events = [e for e in lead.events.all() if "bank loan" in e.text.lower()]
    return render(request, "portal/loan.html", {"lead": lead, "loan": loan, "saved": bool(loan.pk), "people": people, "events": events,
                                                 "slow": bool(loan.pk and loan.active and loan.waiting_days > SLOW_DAYS)})


def pending():
    """Loans still waiting (for the project dashboard)."""
    today = timezone.localdate()
    items = []
    for ln in BankLoan.objects.filter(status__in=BankLoan.ACTIVE).select_related("lead", "owner"):
        late = bool(ln.expected_on and ln.expected_on < today)
        items.append({"loan": ln, "days": ln.waiting_days, "late": late, "slow": ln.waiting_days > SLOW_DAYS})
    items.sort(key=lambda i: (-(i["loan"].status == BankLoan.REJECTED), -i["days"]))
    return {"items": items, "n": len(items), "amount": sum(i["loan"].amount for i in items),
            "late": sum(1 for i in items if i["late"] or i["slow"]), "rejected": sum(1 for i in items if i["loan"].status == BankLoan.REJECTED)}


def run_reminders(dry=False, say=print):
    """Daily: the person following a loan gets a task when it is past its expected date, has waited too long, or was rejected."""
    today = timezone.localdate()
    tt = TaskType.objects.get_or_create(name="Bank loan follow-up")[0]
    made = 0
    for ln in BankLoan.objects.filter(status__in=BankLoan.ACTIVE).select_related("lead", "owner"):
        person = ln.owner or _owner_default()
        if not person:
            continue
        if ln.status == BankLoan.REJECTED:
            why = "Loan rejected: decide - switch to own money / another bank, or mark Lost"
        elif ln.expected_on and ln.expected_on < today:
            why = "Loan not sanctioned yet, expected %s: please chase the bank" % ln.expected_on.strftime("%d %b")
        elif ln.waiting_days > SLOW_DAYS:
            why = "Loan waiting for %d days: please chase the bank" % ln.waiting_days
        else:
            continue
        tag = "[auto:loan:%d]" % ln.pk
        if Task.objects.filter(assigned_to=person, details__contains=tag, done=False).exists():
            continue
        made += 1
        say("   loan task -> %s: %s - %s" % (person.username, ln.lead.customer_name, why))
        if not dry:
            Task.objects.create(task_type=tt, details="%s - %s %s" % (ln.lead.customer_name, why, tag), created_by=None, assigned_to=person, due_date=today)
    return made
