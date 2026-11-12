from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0002_sales_target")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="director",
            field=models.BooleanField(default=False, help_text="Directors see the sales dashboard (everyone's targets) even without a target of their own."),
        ),
    ]
