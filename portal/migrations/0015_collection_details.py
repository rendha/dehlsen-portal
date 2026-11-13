from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0014_payment")]

    operations = [
        migrations.AddField(model_name="collection", name="segment", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="collection", name="system_type", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="collection", name="almm", field=models.CharField(blank=True, max_length=10, verbose_name="DCR / NDCR")),
        migrations.AddField(model_name="collection", name="panel", field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name="collection", name="inverter", field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name="collection", name="work_status", field=models.CharField(blank=True, max_length=60)),
        migrations.AddField(model_name="collection", name="phone", field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name="payment", name="from_sheet", field=models.BooleanField(default=False)),
        migrations.AlterField(model_name="payment", name="date", field=models.DateField(blank=True, null=True, help_text="Empty for old payments whose date the sheet did not have.")),
    ]
