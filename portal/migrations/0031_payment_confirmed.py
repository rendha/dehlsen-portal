import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0030_bankloan'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='confirmed',
            field=models.BooleanField(default=True, help_text='A payment typed by a sales person waits here until Accounts confirms it with the bank. Only confirmed payments count in Collection.received.'),
        ),
        migrations.AddField(
            model_name='payment',
            name='confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='payment',
            name='confirmed_on',
            field=models.DateField(blank=True, null=True),
        ),
    ]
