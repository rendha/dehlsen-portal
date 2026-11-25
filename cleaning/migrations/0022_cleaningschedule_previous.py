import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("cleaning", "0021_cleaningschedule_reason")]

    operations = [
        migrations.AddField(
            model_name="cleaningschedule",
            name="previous",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="next_visits", to="cleaning.cleaningschedule"),
        ),
    ]
