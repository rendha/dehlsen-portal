import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def old_ones_are_checked(apps, schema_editor):
    """Payments that already existed are not shown as new: only payments entered from now on wait for the bank tick."""
    apps.get_model("portal", "Payment").objects.update(bank_checked=True)


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0031_payment_confirmed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="payment", name="bank_checked", field=models.BooleanField(default=False, help_text="Accounts ticks this once the money is seen in the bank statement.")),
        migrations.AddField(model_name="payment", name="bank_checked_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="payment", name="bank_checked_on", field=models.DateField(blank=True, null=True)),
        migrations.RunPython(old_ones_are_checked, migrations.RunPython.noop),
    ]
