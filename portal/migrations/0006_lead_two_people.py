import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0005_lead"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="assigned_to2",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads_assigned2", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="lead",
            name="need",
            field=models.CharField(choices=[("call", "Call"), ("visit", "Site visit"), ("both", "Call + Site visit")], default="call", max_length=10),
        ),
    ]
