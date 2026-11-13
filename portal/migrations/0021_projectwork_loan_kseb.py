from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0020_projectwork")]

    operations = [
        migrations.AddField("projectwork", "payment_mode", models.CharField(choices=[("cash", "Own money / cash"), ("loan", "Bank loan")], default="cash", max_length=5)),
        migrations.AddField("projectwork", "loan_amount", models.DecimalField(decimal_places=2, default=0, help_text="Total the bank gives, e.g. 200000", max_digits=12)),
        migrations.AddField("projectwork", "bank1_amount", models.DecimalField(decimal_places=2, default=140000, help_text="Paid after sanction, before work starts", max_digits=12, verbose_name="bank stage 1 amount")),
        migrations.AddField("projectwork", "loan_sanctioned_on", models.DateField(blank=True, null=True)),
        migrations.AddField("projectwork", "bank1_received_on", models.DateField(blank=True, null=True)),
        migrations.AddField("projectwork", "bank2_received_on", models.DateField(blank=True, null=True)),
        migrations.AddField("projectwork", "feasibility_date", models.DateField(blank=True, null=True)),
        migrations.AddField("projectwork", "registration_paid", models.BooleanField(default=False, verbose_name="KSEB registration fee paid")),
        migrations.AddField("projectwork", "handover_date", models.DateField(blank=True, null=True)),
    ]
