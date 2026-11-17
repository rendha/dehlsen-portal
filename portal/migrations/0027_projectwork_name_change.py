from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0026_projectwork_master_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectwork',
            name='name_change',
            field=models.CharField(blank=True, help_text='Required / Done (empty = not needed)', max_length=20, verbose_name='name change required'),
        ),
    ]
