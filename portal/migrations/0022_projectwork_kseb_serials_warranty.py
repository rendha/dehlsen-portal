from django.db import migrations, models


def money():
    return models.DecimalField(decimal_places=2, default=0, max_digits=12)


class Migration(migrations.Migration):

    dependencies = [("portal", "0021_projectwork_loan_kseb")]

    operations = [
        migrations.AddField("projectwork", "kseb", models.JSONField(blank=True, default=dict)),
        migrations.AddField("projectwork", "kseb_consumer_no", models.CharField(blank=True, max_length=30)),
        migrations.AddField("projectwork", "arn", models.CharField(blank=True, max_length=40, verbose_name="PM Surya Ghar application no.")),
        migrations.AddField("projectwork", "scheme", models.CharField(blank=True, max_length=40)),
        migrations.AddField("projectwork", "panel_count", models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField("projectwork", "panel_serials", models.TextField(blank=True, help_text="All panel serial numbers, separated by commas")),
        migrations.AddField("projectwork", "inverter_serial", models.CharField(blank=True, max_length=60)),
        migrations.AddField("projectwork", "energy_meter_serial", models.CharField(blank=True, max_length=60)),
        migrations.AddField("projectwork", "net_meter_serial", models.CharField(blank=True, max_length=60)),
        migrations.AddField("projectwork", "electrical_contractor", models.CharField(blank=True, max_length=60)),
        migrations.AddField("projectwork", "electrical_amount", money()),
        migrations.AddField("projectwork", "electrical_paid", money()),
        migrations.AddField("projectwork", "structure_contractor", models.CharField(blank=True, max_length=60)),
        migrations.AddField("projectwork", "structure_amount", money()),
        migrations.AddField("projectwork", "structure_paid", money()),
        migrations.AddField("projectwork", "invoice_no", models.CharField(blank=True, max_length=40)),
        migrations.AddField("projectwork", "invoice_date", models.DateField(blank=True, null=True)),
        migrations.AddField("projectwork", "panel_warranty_yrs", models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField("projectwork", "inverter_warranty_yrs", models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField("projectwork", "workmanship_yrs", models.PositiveSmallIntegerField(blank=True, help_text="Empty = 5 years", null=True)),
    ]
