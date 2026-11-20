from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("quotations", "0028_addon_quotation")]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="other_inverter_phase",
            field=models.CharField(blank=True, default="", help_text="Phase of a hand-entered ('Other') inverter: single / three (empty = same as the house)", max_length=10),
        ),
    ]
