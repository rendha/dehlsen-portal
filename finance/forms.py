from django import forms

from .models import Invoice, Payment, Proforma, Vendor


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        kw.setdefault("format", "%Y-%m-%d")
        super().__init__(**kw)


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "credit_days", "gst_no", "contact", "phone", "notes", "is_active"]


class ProformaForm(forms.ModelForm):
    class Meta:
        model = Proforma
        fields = ["vendor", "number", "date", "company", "delivery_to", "customer_name", "description", "amount", "pdf_link"]
        widgets = {"date": DateInput()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["vendor", "number", "date", "company", "delivery_to", "customer_name", "description", "amount", "credit_days",
                  "material_received", "received_on", "pdf_link", "remarks", "proforma"]
        widgets = {"date": DateInput(), "received_on": DateInput()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["proforma"].required = False
        self.fields["proforma"].label = "From proforma (if any)"

    def clean(self):
        d = super().clean()
        pf, vendor = d.get("proforma"), d.get("vendor")
        if pf and vendor and pf.vendor_id != vendor.id:
            self.add_error("proforma", "This proforma belongs to another vendor.")
        return d


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["paid_on", "amount", "fee", "mode", "reference", "note"]
        widgets = {"paid_on": DateInput()}
