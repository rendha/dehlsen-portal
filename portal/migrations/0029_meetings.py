import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0028_crewassignment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Meeting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('date', models.DateField(db_index=True)),
                ('time', models.TimeField(blank=True, null=True)),
                ('venue', models.CharField(blank=True, max_length=200)),
                ('objective', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('held', 'Held'), ('cancelled', 'Cancelled')], default='scheduled', max_length=12)),
                ('prepared_by', models.CharField(blank=True, max_length=120)),
                ('approved_by', models.CharField(blank=True, max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conducted_by', models.ForeignKey(blank=True, help_text='The person who conducts the meeting and keeps its minutes', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('follow_up_of', models.ForeignKey(blank=True, help_text='The earlier meeting whose unfinished items are checked in this one', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='follow_ups', to='portal.meeting')),
            ],
            options={'ordering': ['-date', '-id']},
        ),
        migrations.CreateModel(
            name='MeetingAttendee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, help_text='For people without a portal login', max_length=120)),
                ('present', models.BooleanField(default=False)),
                ('meeting', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendees', to='portal.meeting')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['id']},
        ),
        migrations.CreateModel(
            name='MeetingPoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('notes', models.TextField(blank=True, help_text='What was discussed and decided')),
                ('position', models.PositiveIntegerField(default=0)),
                ('meeting', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='points', to='portal.meeting')),
            ],
            options={'ordering': ['position', 'id']},
        ),
        migrations.CreateModel(
            name='MeetingAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=500)),
                ('owner_name', models.CharField(blank=True, help_text='For people without a portal login', max_length=120)),
                ('target_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('open', 'Open'), ('progress', 'In progress'), ('done', 'Done'), ('dropped', 'Dropped')], default='open', max_length=10)),
                ('done_on', models.DateField(blank=True, null=True)),
                ('remark', models.CharField(blank=True, max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('meeting', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='portal.meeting')),
                ('owner_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='meeting_actions', to=settings.AUTH_USER_MODEL)),
                ('point', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='actions', to='portal.meetingpoint')),
            ],
            options={'ordering': ['id']},
        ),
    ]
