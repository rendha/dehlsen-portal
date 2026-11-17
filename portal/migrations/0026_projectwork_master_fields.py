from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0025_lead_due_dates'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectwork',
            name='email',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='alt_phone',
            field=models.CharField(blank=True, max_length=40, verbose_name='alternate phone'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='pincode',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='district',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='region',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='segment',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='load_change',
            field=models.CharField(blank=True, max_length=20, verbose_name='load change required'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='almm',
            field=models.CharField(blank=True, max_length=10, verbose_name='ALMM (DCR / NDCR)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='project_stage',
            field=models.CharField(blank=True, max_length=40, help_text='Stage from the Project Master (the ticks decide it once work is ticked)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='quote_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='quote value (from the master sheet)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='panel_wp',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=7, null=True, verbose_name='panel wattage (Wp)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='dc_kwp',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='DC capacity (kWp)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='ac_kw',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='AC / inverter capacity (kW)'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='inverter_phase',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='inverter_model',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='roof_type',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='panel_at_site',
            field=models.BooleanField(blank=True, null=True, verbose_name='panel material at site'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='inverter_at_site',
            field=models.BooleanField(blank=True, null=True, verbose_name='inverter material at site'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='energy_meter_make',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='net_meter_make',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='kseb_ref',
            field=models.CharField(blank=True, max_length=40, verbose_name='KSEB application / ref. no.'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='docs_status',
            field=models.CharField(blank=True, max_length=30, verbose_name='KSEB documents status'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='reg_receipt',
            field=models.CharField(blank=True, max_length=40, verbose_name='registration fee receipt no.'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='inspection_status',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='subsidy_status',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='bank_details',
            field=models.CharField(blank=True, max_length=10, verbose_name='bank details submitted on portal'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='programming_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='kseb_notes',
            field=models.TextField(blank=True, verbose_name='blocker / notes'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='handover_status',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='handover_mode',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='handed_over_by',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='docs_given',
            field=models.JSONField(blank=True, default=dict, verbose_name='documents given to the customer'),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='invoice_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='warranty_start',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='projectwork',
            name='panel_perf_yrs',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='panel performance warranty (yrs)'),
        ),
    ]
