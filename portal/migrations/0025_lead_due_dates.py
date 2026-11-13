from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("portal", "0024_projectwork_quotation_id")]

    operations = [
        migrations.AddField("lead", "site_visit_by", models.DateField(blank=True, help_text="The date the site visit must be done by (optional)", null=True, verbose_name="site visit by")),
        migrations.AddField("lead", "quotation_by", models.DateField(blank=True, help_text="The date the quotation must be given by (optional)", null=True, verbose_name="quotation by")),
    ]
