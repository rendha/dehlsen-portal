from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0007_lead_need_other")]

    operations = [
        migrations.AddField(model_name="lead", name="quotation_id", field=models.PositiveIntegerField(blank=True, null=True, help_text="The quotation made for this lead (the latest one is shown)")),
        migrations.AddField(model_name="lead", name="lost", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="lead", name="lost_reason", field=models.CharField(blank=True, max_length=100)),
    ]
