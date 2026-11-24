from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("quotations", "0029_quotation_other_inverter_phase")]
    operations = [migrations.AddField("quotation", "lost", models.BooleanField(default=False))]
