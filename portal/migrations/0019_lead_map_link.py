from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0018_collection_sheet_fields_again"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="map_link",
            field=models.CharField(blank=True, help_text="A Google Maps link, or latitude,longitude, or an address (optional)", max_length=500, verbose_name="Google Maps location"),
        ),
    ]
