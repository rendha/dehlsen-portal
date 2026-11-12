import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0004_places"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_name", models.CharField(max_length=120)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("area", models.CharField(blank=True, max_length=100, verbose_name="place")),
                ("need", models.CharField(choices=[("call", "Call"), ("visit", "Site visit")], default="call", max_length=10)),
                ("priority", models.CharField(choices=[("hot", "Hot"), ("medium", "Medium"), ("cold", "Cold")], default="medium", max_length=10)),
                ("note", models.TextField(blank=True)),
                ("done", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads_assigned", to=settings.AUTH_USER_MODEL)),
                ("entered_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leads_entered", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["done", "-created_at"]},
        ),
    ]
