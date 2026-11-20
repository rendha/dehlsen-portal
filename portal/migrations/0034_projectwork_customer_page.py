from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0033_lead_no"),
    ]

    operations = [
        migrations.AddField(model_name="projectwork", name="track_token", field=models.CharField(blank=True, db_index=True, help_text="The private link the customer opens to see the schedule (made when first needed)", max_length=40)),
        migrations.AddField(model_name="projectwork", name="customer_plan", field=models.JSONField(blank=True, default=dict, help_text="Planned dates shown to the customer, by step key")),
    ]
