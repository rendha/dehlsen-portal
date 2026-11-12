import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("whatsapp", models.CharField(blank=True, help_text="With country code, e.g. 919876543210 (a 10-digit number is taken as Indian).", max_length=30, verbose_name="WhatsApp number")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="portal_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TaskType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TaskPerson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.CharField(blank=True, help_text="Shown next to the name, e.g. the area", max_length=100)),
                ("task_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignments", to="portal.tasktype")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="taskperson",
            constraint=models.UniqueConstraint(fields=("task_type", "user"), name="unique_task_person"),
        ),
        migrations.AddField(
            model_name="tasktype",
            name="people",
            field=models.ManyToManyField(blank=True, help_text="The people who do this task", related_name="task_types", through="portal.TaskPerson", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("details", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("due_date", models.DateField()),
                ("due_time", models.TimeField(blank=True, null=True)),
                ("done", models.BooleanField(default=False)),
                ("done_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks_received", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks_given", to=settings.AUTH_USER_MODEL)),
                ("task_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="portal.tasktype")),
            ],
            options={"ordering": ["due_date", "due_time", "id"]},
        ),
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.CharField(max_length=500, unique=True)),
                ("p256dh", models.CharField(max_length=200)),
                ("auth", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
