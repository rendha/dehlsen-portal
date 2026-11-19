"""Accounts: what we owe the vendors.

  Proforma  = a vendor's REQUEST for money (before supply).  It is never counted as owed.
  Invoice   = the vendor's bill for what we really bought.  Only invoices make a payable.
  Payment   = money we paid.  Linked to an invoice, or (an advance) to a proforma that has no invoice yet.
When the invoice of a proforma is entered, the advance paid against that proforma is deducted from the invoice automatically.
"""
import datetime
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

ZERO = Decimal("0")
COMPANIES = [("Dehlsen", "Dehlsen"), ("Reed", "Reed")]
DELIVERY = [("Godown", "Godown"), ("Customer Site", "Customer Site")]
MODES = [("Cash", "Cash"), ("UPI", "UPI"), ("Credit Card", "Credit Card"), ("Cheque", "Cheque"), ("NEFT/RTGS", "NEFT/RTGS")]
SOON_DAYS = 7


class Vendor(models.Model):
    name = models.CharField(max_length=150, unique=True)
    credit_days = models.PositiveIntegerField(default=0, help_text="0 = pay on delivery / cash")
    gst_no = models.CharField("GST no.", max_length=20, blank=True)
    contact = models.CharField("contact person", max_length=100, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Proforma(models.Model):
    PENDING, APPROVED, REJECTED, INVOICED, CANCELLED = "pending", "approved", "rejected", "invoiced", "cancelled"
    STATUSES = [(PENDING, "Waiting for approval"), (APPROVED, "Approved"), (REJECTED, "Rejected"), (INVOICED, "Invoiced"), (CANCELLED, "Cancelled")]
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="proformas")
    number = models.CharField("proforma no.", max_length=60, blank=True)
    date = models.DateField(default=timezone.localdate)
    company = models.CharField(max_length=10, choices=COMPANIES, default="Dehlsen")
    delivery_to = models.CharField(max_length=20, choices=DELIVERY, default="Godown")
    customer_name = models.CharField("customer / site", max_length=150, blank=True)
    description = models.CharField(max_length=300, blank=True)
    amount = models.DecimalField("amount incl. GST", max_digits=12, decimal_places=2, default=ZERO)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    status_note = models.CharField(max_length=300, blank=True)
    pdf_link = models.CharField("PDF link", max_length=500, blank=True)
    check_note = models.CharField(max_length=300, blank=True, help_text="Something to confirm about this entry; shows in the 'To confirm' list")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return "%s %s" % (self.vendor, self.number or self.date)

    @property
    def advance_paid(self):
        """Money paid against this proforma before any invoice (money out, minus bank / card charges)."""
        return sum((p.applied for p in self.payments.filter(invoice__isnull=True)), ZERO)

    @property
    def invoice(self):
        return self.invoices.first()


class Invoice(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="invoices")
    proforma = models.ForeignKey(Proforma, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    number = models.CharField("invoice no.", max_length=60, blank=True)
    date = models.DateField("invoice date", default=timezone.localdate)
    company = models.CharField(max_length=10, choices=COMPANIES, default="Dehlsen")
    delivery_to = models.CharField(max_length=20, choices=DELIVERY, default="Godown")
    customer_name = models.CharField("customer / site", max_length=150, blank=True)
    description = models.CharField(max_length=300, blank=True)
    amount = models.DecimalField("amount incl. GST", max_digits=12, decimal_places=2)
    credit_days = models.PositiveIntegerField(default=0, help_text="Counted from the invoice date. 0 = due at once.")
    material_received = models.BooleanField(default=False)
    received_on = models.DateField(null=True, blank=True)
    approved = models.BooleanField("checked, ready to pay", default=False)
    pdf_link = models.CharField("PDF link", max_length=500, blank=True)
    remarks = models.CharField(max_length=300, blank=True)
    check_note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return "%s %s" % (self.vendor, self.number or self.date)

    @property
    def due_date(self):
        return self.date + datetime.timedelta(days=self.credit_days or 0)

    @property
    def advance_applied(self):
        """The advance paid against this invoice's proforma (only the first invoice of a proforma takes it)."""
        pf = self.proforma
        if pf is None or pf.invoices.order_by("id").values_list("pk", flat=True).first() != self.pk:
            return ZERO
        return pf.advance_paid

    @property
    def paid(self):
        return sum((p.applied for p in self.payments.all()), ZERO)

    @property
    def balance(self):
        return (self.amount or ZERO) - self.paid - self.advance_applied

    @property
    def days_to_due(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def status(self):
        """paid / overdue / soon / part / open"""
        if self.balance <= 0:
            return "paid"
        d = self.days_to_due
        if d < 0:
            return "overdue"
        if d <= SOON_DAYS:
            return "soon"
        return "part" if (self.paid + self.advance_applied) > 0 else "open"


class Payment(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="payments")
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.CASCADE, related_name="payments")
    proforma = models.ForeignKey(Proforma, null=True, blank=True, on_delete=models.CASCADE, related_name="payments")
    paid_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField("money paid out", max_digits=12, decimal_places=2)
    fee = models.DecimalField("of which bank / card charge", max_digits=10, decimal_places=2, default=ZERO,
                              help_text="Part of the amount that is only a charge and does not reduce the bill")
    mode = models.CharField(max_length=15, choices=MODES, blank=True)
    reference = models.CharField("UTR / ref no.", max_length=60, blank=True)
    note = models.CharField(max_length=300, blank=True)
    check_note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_on", "id"]

    @property
    def applied(self):
        return (self.amount or ZERO) - (self.fee or ZERO)
