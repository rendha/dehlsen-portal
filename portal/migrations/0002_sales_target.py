import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="sales_name",
            field=models.CharField(blank=True, help_text="Sales persons only: the name he types in the Quotation For box, if it differs from his first name / username.", max_length=100, verbose_name="name in 'Quotation For'"),
        ),
        migrations.CreateModel(
            name="SalesTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, help_text="e.g. Q4 2026 or FY 2026-27", max_length=60)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="target (Rs)")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_targets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-end_date", "user__username"]},
        ),
    ]
