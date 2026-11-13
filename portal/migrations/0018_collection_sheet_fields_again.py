from django.db import migrations, models


class Migration(migrations.Migration):
    """Puts back the six sheet fields that 0017 removed by mistake (it was generated from an out-of-date models.py)."""

    dependencies = [("portal", "0017_alter_payment_options_remove_collection_deal_value_and_more")]

    operations = [
        migrations.AddField(model_name="collection", name="deal_value", field=models.DecimalField(decimal_places=2, default=0, help_text="Deal value before discount (Rs).", max_digits=14)),
        migrations.AddField(model_name="collection", name="discount", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField(model_name="collection", name="expected_gp", field=models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="expected gross profit")),
        migrations.AddField(model_name="collection", name="incentive_category", field=models.CharField(blank=True, max_length=5)),
        migrations.AddField(model_name="collection", name="site_address", field=models.TextField(blank=True)),
        migrations.AddField(model_name="collection", name="remarks", field=models.TextField(blank=True)),
    ]
