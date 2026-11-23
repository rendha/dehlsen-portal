from django.db import migrations, models


def backfill(apps, schema_editor):
    """Fill the new items from what is already ticked (an estimate: later work implies the earlier delivery/work was done)."""
    W = apps.get_model("portal", "ProjectWork")
    for w in W.objects.all():
        later = w.electrical or w.inv_program or w.testing or w.meter_fix or bool(w.commission_date)
        w.structure_mat = bool(w.structure or later)
        w.meter_mat = bool(w.meter_fix or w.commission_date)
        w.panel_mount = bool(w.panel_done and later)
        w.earthing = bool(later)
        w.save(update_fields=["structure_mat", "meter_mat", "panel_mount", "earthing"])


class Migration(migrations.Migration):
    dependencies = [("portal", "0034_projectwork_customer_page")]
    operations = [
        migrations.AddField("projectwork", "structure_mat", models.BooleanField(default=False, verbose_name="structure material delivered")),
        migrations.AddField("projectwork", "meter_mat", models.BooleanField(default=False, verbose_name="net meter delivered")),
        migrations.AddField("projectwork", "panel_mount", models.BooleanField(default=False, verbose_name="panel mounting")),
        migrations.AddField("projectwork", "earthing", models.BooleanField(default=False, verbose_name="earthing work")),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
