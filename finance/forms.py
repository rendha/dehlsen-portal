from django import forms

from .models import Attachment, Invoice, Payment, Proforma, Vendor


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        kw.setdefault("format", "%Y-%m-%d")
        super().__init__(**kw)


MAX_FILE = 5 * 1024 * 1024
FILE_TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class FileMixin(forms.Form):
    """Adds an upload box (PDF or photo, from phone or computer) and stores the file in the database."""
    pdf_file = forms.FileField(required=False, label="Upload the PDF or a photo of it",
                               help_text="PDF, JPG or PNG up to 5 MB. On a phone you can pick a file or take a photo. Uploading again replaces the old file.",
                               widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,image/*"}))

    def customer_picker(self):
        """Make 'Customer / site' a pick-from-the-list box (you can still type something else)."""
        from store.models import Customer
        names = sorted({n.strip() for n in Customer.objects.values_list("name", flat=True) if n and n.strip()}, key=str.lower)
        self.customer_options = names
        if "customer_name" in self.fields:
            self.fields["customer_name"].widget = forms.TextInput(attrs={"list": "fin-customers", "autocomplete": "off", "placeholder": "Start typing a customer name, or pick from the list"})
            self.fields["customer_name"].help_text = "Pick a customer from the list. You can also type a site name that is not a customer."

    def clean_pdf_file(self):
        up = self.cleaned_data.get("pdf_file")
        if not up or up is False:
            return None
        ext = up.name.rsplit(".", 1)[-1].lower() if "." in up.name else ""
        if ext not in FILE_TYPES:
            raise forms.ValidationError("Upload a PDF, JPG or PNG file.")
        if up.size > MAX_FILE:
            raise forms.ValidationError("The file is over 5 MB. Make it smaller and try again.")
        return up

    def save_file(self, obj):
        up = self.cleaned_data.get("pdf_file")
        if not up:
            return
        ext = up.name.rsplit(".", 1)[-1].lower()
        key = "proforma" if isinstance(obj, Proforma) else "invoice"
        Attachment.objects.update_or_create(**{key: obj}, defaults={"name": up.name[:200], "content_type": FILE_TYPES[ext], "data": up.read()})


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "credit_days", "gst_no", "contact", "phone", "notes", "is_active"]


class ProformaForm(FileMixin, forms.ModelForm):
    class Meta:
        model = Proforma
        fields = ["vendor", "number", "date", "company", "delivery_to", "customer_name", "description", "amount", "pdf_link"]
        widgets = {"date": DateInput()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.customer_picker()


class InvoiceForm(FileMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["vendor", "number", "date", "company", "delivery_to", "customer_name", "description", "amount", "credit_days",
                  "material_received", "received_on", "pdf_link", "remarks", "proforma"]
        widgets = {"date": DateInput(), "received_on": DateInput()}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.customer_picker()
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
