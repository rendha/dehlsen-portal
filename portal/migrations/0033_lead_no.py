from django.db import migrations, models


def number_old_leads(apps, schema_editor):
    """Gives every lead that already exists an ID, oldest first, a fresh series for each financial year."""
    Lead = apps.get_model("portal", "Lead")
    count = {}
    for lead in Lead.objects.order_by("created_at", "id"):
        d = lead.created_at
        year = d.year if d.month >= 4 else d.year - 1
        head = "L%02d-%02d/" % (year % 100, (year + 1) % 100)
        count[head] = count.get(head, 0) + 1
        Lead.objects.filter(pk=lead.pk).update(lead_no="%s%04d" % (head, count[head]))


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0032_payment_bank_checked"),
    ]

    operations = [
        migrations.AddField(model_name="lead", name="lead_no", field=models.CharField(blank=True, db_index=True, help_text="Filled automatically, e.g. L26-27/0012", max_length=20, verbose_name="lead ID")),
        migrations.RunPython(number_old_leads, migrations.RunPython.noop),
    ]
