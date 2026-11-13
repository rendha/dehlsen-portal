import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0019_lead_map_link"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectWork",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("name_key", models.CharField(blank=True, db_index=True, max_length=200)),
                ("project_id", models.CharField(blank=True, max_length=30)),
                ("kw", models.CharField(blank=True, max_length=20)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("location", models.CharField(blank=True, max_length=150)),
                ("site_address", models.TextField(blank=True)),
                ("map_link", models.CharField(blank=True, max_length=500)),
                ("system", models.CharField(blank=True, max_length=40)),
                ("panel_make", models.CharField(blank=True, max_length=60)),
                ("inverter_make", models.CharField(blank=True, max_length=60)),
                ("booking_date", models.DateField(blank=True, null=True)),
                ("site_estimation", models.BooleanField(default=False)),
                ("design", models.BooleanField(default=False)),
                ("bos", models.BooleanField(default=False, verbose_name="BOS")),
                ("inverter_done", models.BooleanField(default=False, verbose_name="inverter")),
                ("panel_done", models.BooleanField(default=False, verbose_name="panel")),
                ("electrical", models.BooleanField(default=False, verbose_name="electrical work")),
                ("structure", models.BooleanField(default=False, verbose_name="structure work")),
                ("inv_program", models.BooleanField(default=False, verbose_name="inverter programming")),
                ("testing", models.BooleanField(default=False)),
                ("meter_fix", models.BooleanField(default=False)),
                ("wifi", models.BooleanField(blank=True, null=True, verbose_name="Wi-Fi connected")),
                ("work_status", models.CharField(blank=True, help_text="What is holding it / where it is, e.g. waiting for documentation", max_length=300)),
                ("commission_date", models.DateField(blank=True, null=True)),
                ("handover", models.BooleanField(default=False, verbose_name="documents handed over")),
                ("handover_note", models.CharField(blank=True, max_length=200)),
                ("feasibility", models.CharField(blank=True, choices=[("", "Not checked"), ("ok", "Feasible"), ("issue", "Feasibility issue")], default="", max_length=10)),
                ("feasibility_note", models.CharField(blank=True, max_length=300)),
                ("estimator", models.CharField(blank=True, max_length=60)),
                ("structure_estimation", models.CharField(blank=True, max_length=60)),
                ("material_dispatched", models.BooleanField(blank=True, null=True)),
                ("remarks", models.CharField(blank=True, max_length=300)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("collection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="works", to="portal.collection")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
    ]
