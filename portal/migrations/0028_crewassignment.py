import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0027_projectwork_name_change'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CrewAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('team', models.CharField(help_text='Contractor or worker names', max_length=200)),
                ('work', models.CharField(choices=[('Electrical', 'Electrical'), ('Structure', 'Structure'), ('Panel fixing', 'Panel fixing'), ('Inverter', 'Inverter'), ('Earthing / civil', 'Earthing / civil'), ('Testing', 'Testing'), ('Site visit / survey', 'Site visit / survey'), ('Material delivery', 'Material delivery'), ('Other', 'Other')], default='Electrical', max_length=30)),
                ('site', models.CharField(blank=True, help_text='Site typed by hand when it is not a project', max_length=200)),
                ('note', models.CharField(blank=True, max_length=300)),
                ('status', models.CharField(choices=[('planned', 'Planned'), ('done', 'Done'), ('cancelled', 'Cancelled')], default='planned', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crew_visits', to='portal.projectwork')),
            ],
            options={'ordering': ['date', 'work', 'team', 'id']},
        ),
    ]
