from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0012_collection")]

    operations = [
        migrations.AddField(model_name="collection", name="quotation_id", field=models.IntegerField(blank=True, db_index=True, null=True, help_text="The confirmed quotation this came from (filled automatically).")),
    ]
