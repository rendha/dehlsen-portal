from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("finance", "0002_attachment")]

    operations = [
        migrations.AddField(
            model_name="proforma",
            name="buy_by",
            field=models.DateField(blank=True, help_text="The proforma is valid only until this date. Purchase the material before it.", null=True, verbose_name="buy by (last date to purchase)"),
        ),
    ]
