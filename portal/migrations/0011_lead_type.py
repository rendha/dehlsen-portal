from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0010_site_details")]

    operations = [
        migrations.AddField(model_name="lead", name="customer_type", field=models.CharField(blank=True, choices=[("residential", "Residential"), ("commercial", "Commercial"), ("industrial", "Industrial")], max_length=15)),
        migrations.AddField(model_name="lead", name="dcr_choice", field=models.CharField(blank=True, choices=[("dcr", "DCR"), ("non_dcr", "Non-DCR"), ("undecided", "DCR / Non-DCR not decided")], help_text="Only for residential leads", max_length=10)),
        migrations.AddField(model_name="lead", name="system_type", field=models.CharField(blank=True, choices=[("on_grid", "On-grid"), ("off_grid", "Off-grid"), ("hybrid", "Hybrid"), ("other", "Other")], max_length=10)),
        migrations.AddField(model_name="lead", name="system_other", field=models.CharField(blank=True, max_length=100, verbose_name="system type (other)")),
    ]
