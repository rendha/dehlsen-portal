from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0006_lead_two_people")]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="need",
            field=models.CharField(default="call", help_text="call, visit, other - separated by commas", max_length=60),
        ),
        migrations.AddField(
            model_name="lead",
            name="need_other",
            field=models.CharField(blank=True, max_length=200, verbose_name="what to do (other)"),
        ),
    ]
