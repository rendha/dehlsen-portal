from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0012_alter_salestarget_label")]

    operations = [
        migrations.CreateModel(
            name="Collection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_id", models.CharField(max_length=30, unique=True)),
                ("booking_date", models.DateField(blank=True, null=True)),
                ("customer", models.CharField(max_length=150)),
                ("region", models.CharField(blank=True, max_length=60)),
                ("sales_name", models.CharField(help_text="The sales person, as named in the sheet (Huda, Fouzan ...).", max_length=60)),
                ("kw", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("net_value", models.DecimalField(decimal_places=2, default=0, help_text="Deal value minus discount (Rs).", max_digits=14)),
                ("received", models.DecimalField(decimal_places=2, default=0, help_text="Total collected so far (Rs).", max_digits=14)),
            ],
            options={"ordering": ["-booking_date", "project_id"]},
        ),
    ]
