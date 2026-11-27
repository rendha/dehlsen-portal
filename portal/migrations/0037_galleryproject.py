from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def photos_to_projects(apps, schema_editor):
    """Every photo already in the gallery becomes a project of its own (with its details), so nothing is lost."""
    Photo = apps.get_model("portal", "GalleryPhoto")
    Project = apps.get_model("portal", "GalleryProject")
    for ph in Photo.objects.all().order_by("id"):
        pr = Project.objects.create(title=ph.title, place=ph.place, capacity=ph.capacity, kind=ph.kind,
                                    created_at=ph.created_at, cover=ph)
        Photo.objects.filter(pk=ph.pk).update(project=pr)


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0036_galleryphoto"),
    ]

    operations = [
        migrations.CreateModel(
            name="GalleryProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=120)),
                ("place", models.CharField(blank=True, max_length=100)),
                ("capacity", models.CharField(blank=True, help_text="for example 5 kW", max_length=30, verbose_name="capacity")),
                ("kind", models.CharField(choices=[("home", "House"), ("flat", "Flat / Apartment"), ("commercial", "Commercial"), ("industrial", "Industrial"), ("other", "Other")], default="home", max_length=12)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("cover", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="portal.galleryphoto")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddField(
            model_name="galleryphoto",
            name="project",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="portal.galleryproject"),
        ),
        migrations.AddField(
            model_name="galleryphoto",
            name="source",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.RunPython(photos_to_projects, migrations.RunPython.noop),
    ]
