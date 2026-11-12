import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0003_profile_director"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Place",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="profile",
            name="place",
            field=models.ForeignKey(blank=True, help_text="The sales area of this person.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="members", to="portal.place"),
        ),
        migrations.AddField(
            model_name="salestarget",
            name="place",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="targets", to="portal.place"),
        ),
        migrations.AddField(
            model_name="salestarget",
            name="fixed_achieved",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Leave empty to count it from the confirmed customers. Fill it for a finished quarter.", max_digits=14, null=True, verbose_name="fixed achieved (Rs)"),
        ),
        migrations.AlterField(
            model_name="salestarget",
            name="user",
            field=models.ForeignKey(blank=True, help_text="Fill the place OR the person, not both.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sales_targets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterModelOptions(
            name="salestarget",
            options={"ordering": ["-end_date", "place__name", "user__username"]},
        ),
    ]
