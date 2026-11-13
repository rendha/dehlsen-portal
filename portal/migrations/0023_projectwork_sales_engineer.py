from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0022_projectwork_kseb_serials_warranty")]

    operations = [
        migrations.AddField("projectwork", "sales_person", models.CharField(blank=True, help_text="Whose customer this is", max_length=60)),
        migrations.AddField("projectwork", "engineer", models.CharField(blank=True, max_length=60, verbose_name="site in-charge / engineer")),
    ]
