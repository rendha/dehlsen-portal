import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0008_lead_quotation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="lead", name="next_step", field=models.CharField(blank=True, max_length=100, help_text="What has to happen next, e.g. Site visit")),
        migrations.CreateModel(
            name="LeadEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(blank=True, max_length=20)),
                ("text", models.CharField(max_length=400)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="portal.lead")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
