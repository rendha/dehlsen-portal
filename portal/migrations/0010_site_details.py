import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0009_lead_history"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteDetails",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("roof_length", models.CharField(blank=True, max_length=60, verbose_name="roof length")),
                ("roof_width", models.CharField(blank=True, max_length=60, verbose_name="roof width")),
                ("roof_layout", models.TextField(blank=True, verbose_name="roof / plant layout")),
                ("inverter_position", models.CharField(blank=True, max_length=200)),
                ("acdb_position", models.CharField(blank=True, max_length=200, verbose_name="ACDB position")),
                ("dcdb_position", models.CharField(blank=True, max_length=200, verbose_name="DCDB position")),
                ("earth_rod_position", models.CharField(blank=True, max_length=200)),
                ("cable_laying", models.TextField(blank=True, verbose_name="cable laying")),
                ("meter_position", models.CharField(blank=True, max_length=200)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("lead", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="site", to="portal.lead")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SitePhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.BinaryField()),
                ("content_type", models.CharField(default="image/jpeg", max_length=60)),
                ("caption", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="portal.lead")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
