import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0006_gst_percent'),
    ]

    operations = [
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('note', models.CharField(blank=True, max_length=250)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Purchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=300)),
                ('invoice_no', models.CharField(blank=True, max_length=60)),
                ('ordered_on', models.DateField(default=django.utils.timezone.localdate)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('credit', models.BooleanField(default=False)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('expected_on', models.DateField(blank=True, null=True)),
                ('received_on', models.DateField(blank=True, null=True)),
                ('note', models.CharField(blank=True, max_length=250)),
                ('created_by', models.CharField(blank=True, max_length=150)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchases', to='store.customer')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchases', to='store.supplier')),
            ],
            options={'ordering': ['-ordered_on', '-id']},
        ),
        migrations.CreateModel(
            name='SupplierPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('paid_on', models.DateField(default=django.utils.timezone.localdate)),
                ('mode', models.CharField(choices=[('cash', 'Cash'), ('bank', 'Bank transfer'), ('upi', 'UPI'), ('cheque', 'Cheque'), ('other', 'Other')], default='bank', max_length=10)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('recorded_by', models.CharField(blank=True, max_length=150)),
                ('purchase', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='store.purchase')),
            ],
            options={'ordering': ['paid_on', 'id']},
        ),
    ]
