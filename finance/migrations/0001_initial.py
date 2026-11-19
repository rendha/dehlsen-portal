import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True)),
                ("credit_days", models.PositiveIntegerField(default=0, help_text="0 = pay on delivery / cash")),
                ("gst_no", models.CharField(blank=True, max_length=20, verbose_name="GST no.")),
                ("contact", models.CharField(blank=True, max_length=100, verbose_name="contact person")),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Proforma",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(blank=True, max_length=60, verbose_name="proforma no.")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("company", models.CharField(choices=[("Dehlsen", "Dehlsen"), ("Reed", "Reed")], default="Dehlsen", max_length=10)),
                ("delivery_to", models.CharField(choices=[("Godown", "Godown"), ("Customer Site", "Customer Site")], default="Godown", max_length=20)),
                ("customer_name", models.CharField(blank=True, max_length=150, verbose_name="customer / site")),
                ("description", models.CharField(blank=True, max_length=300)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12, verbose_name="amount incl. GST")),
                ("status", models.CharField(choices=[("pending", "Waiting for approval"), ("approved", "Approved"), ("rejected", "Rejected"), ("invoiced", "Invoiced"), ("cancelled", "Cancelled")], default="pending", max_length=10)),
                ("status_note", models.CharField(blank=True, max_length=300)),
                ("pdf_link", models.CharField(blank=True, max_length=500, verbose_name="PDF link")),
                ("check_note", models.CharField(blank=True, help_text="Something to confirm about this entry; shows in the 'To confirm' list", max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proformas", to="finance.vendor")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(blank=True, max_length=60, verbose_name="invoice no.")),
                ("date", models.DateField(default=django.utils.timezone.localdate, verbose_name="invoice date")),
                ("company", models.CharField(choices=[("Dehlsen", "Dehlsen"), ("Reed", "Reed")], default="Dehlsen", max_length=10)),
                ("delivery_to", models.CharField(choices=[("Godown", "Godown"), ("Customer Site", "Customer Site")], default="Godown", max_length=20)),
                ("customer_name", models.CharField(blank=True, max_length=150, verbose_name="customer / site")),
                ("description", models.CharField(blank=True, max_length=300)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="amount incl. GST")),
                ("credit_days", models.PositiveIntegerField(default=0, help_text="Counted from the invoice date. 0 = due at once.")),
                ("material_received", models.BooleanField(default=False)),
                ("received_on", models.DateField(blank=True, null=True)),
                ("approved", models.BooleanField(default=False, verbose_name="checked, ready to pay")),
                ("pdf_link", models.CharField(blank=True, max_length=500, verbose_name="PDF link")),
                ("remarks", models.CharField(blank=True, max_length=300)),
                ("check_note", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("proforma", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices", to="finance.proforma")),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="finance.vendor")),
            ],
            options={"ordering": ["date", "id"]},
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paid_on", models.DateField(default=django.utils.timezone.localdate)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="money paid out")),
                ("fee", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="Part of the amount that is only a charge and does not reduce the bill", max_digits=10, verbose_name="of which bank / card charge")),
                ("mode", models.CharField(blank=True, choices=[("Cash", "Cash"), ("UPI", "UPI"), ("Credit Card", "Credit Card"), ("Cheque", "Cheque"), ("NEFT/RTGS", "NEFT/RTGS")], max_length=15)),
                ("reference", models.CharField(blank=True, max_length=60, verbose_name="UTR / ref no.")),
                ("note", models.CharField(blank=True, max_length=300)),
                ("check_note", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="finance.invoice")),
                ("proforma", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="finance.proforma")),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="finance.vendor")),
            ],
            options={"ordering": ["paid_on", "id"]},
        ),
    ]
