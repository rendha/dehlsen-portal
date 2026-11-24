import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("finance", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("content_type", models.CharField(max_length=60)),
                ("data", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("invoice", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachment", to="finance.invoice")),
                ("proforma", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachment", to="finance.proforma")),
            ],
        ),
    ]
