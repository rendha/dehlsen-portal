from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0023_projectwork_sales_engineer")]

    operations = [
        migrations.AddField("projectwork", "quotation_id", models.IntegerField(blank=True, db_index=True, help_text="The confirmed quotation of this customer (filled automatically)", null=True)),
    ]
