from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0037_galleryproject"),
    ]

    operations = [
        migrations.RemoveField(model_name="galleryphoto", name="title"),
        migrations.RemoveField(model_name="galleryphoto", name="place"),
        migrations.RemoveField(model_name="galleryphoto", name="capacity"),
        migrations.RemoveField(model_name="galleryphoto", name="kind"),
        migrations.AlterField(
            model_name="galleryphoto",
            name="project",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="portal.galleryproject"),
        ),
    ]
