from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("cleaning", "0020_schedule_partially_done")]

    operations = [
        migrations.AddField(
            model_name="cleaningschedule",
            name="reason",
            field=models.CharField(blank=True, default="", max_length=300),
            preserve_default=False,
        ),
    ]
