from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("store", "0005_customer_quoted_total")]

    operations = [
        migrations.AddField(model_name=name, name="gst_percent", field=models.DecimalField(
            blank=True, decimal_places=2, max_digits=5, null=True,
            help_text="Leave empty to use the standard rate: 5 for solar panels and inverters, 18 for everything else"))
        for name in ("stock", "bositem", "line")
    ]
