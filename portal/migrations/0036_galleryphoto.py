from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0035_projectwork_weighted_items"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GalleryPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=120)),
                ("place", models.CharField(blank=True, max_length=100)),
                ("capacity", models.CharField(blank=True, help_text="for example 5 kW", max_length=30, verbose_name="capacity")),
                ("kind", models.CharField(choices=[("home", "House"), ("flat", "Flat / Apartment"), ("commercial", "Commercial"), ("industrial", "Industrial"), ("other", "Other")], default="home", max_length=12)),
                ("data", models.BinaryField()),
                ("thumb", models.BinaryField()),
                ("content_type", models.CharField(default="image/jpeg", max_length=60)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
