import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0029_meetings'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BankLoan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bank', models.CharField(blank=True, max_length=100)),
                ('branch', models.CharField(blank=True, max_length=100)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='loan amount applied for')),
                ('applied_on', models.DateField(blank=True, null=True)),
                ('expected_on', models.DateField(blank=True, null=True, verbose_name='expected sanction date')),
                ('status', models.CharField(choices=[('docs', 'Documents being collected'), ('applied', 'Applied'), ('query', 'Query from bank'), ('sanctioned', 'Sanctioned'), ('rejected', 'Rejected - decide'), ('cash', 'Switched to own money'), ('lost', 'Lost (loan rejected)')], default='docs', max_length=12)),
                ('notes', models.TextField(blank=True)),
                ('reject_reason', models.CharField(blank=True, max_length=200)),
                ('sanctioned_on', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('lead', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='loan', to='portal.lead')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loans_followed', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
