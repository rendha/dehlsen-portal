from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Collection, Payment, Lead, SiteDetails, Place, Profile, PushSubscription, SalesTarget, Task, TaskPerson, TaskType

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 1
    max_num = 1


class PortalUserAdmin(UserAdmin):
    """The normal user page, with the WhatsApp number added at the bottom."""
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "is_active")


admin.site.unregister(User)
admin.site.register(User, PortalUserAdmin)


class TaskPersonInline(admin.TabularInline):
    model = TaskPerson
    extra = 3
    verbose_name = "person who does this task"
    verbose_name_plural = "people who do this task (the note is shown next to the name, e.g. an area)"


@admin.register(TaskType)
class TaskTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "who")
    inlines = [TaskPersonInline]
    search_fields = ("name",)

    @admin.display(description="People who do it")
    def who(self, obj):
        return ", ".join(u.get_full_name() or u.get_username() for u in obj.people.all()) or "- nobody yet -"


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_type", "assigned_to", "created_by", "created_at", "due_date", "done")
    list_filter = ("done", "task_type", "assigned_to")
    date_hierarchy = "due_date"


admin.site.register(PushSubscription)


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "people")

    @admin.display(description="People")
    def people(self, obj):
        return ", ".join(p.user.get_full_name() or p.user.get_username() for p in obj.members.select_related("user")) or "-"


@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    """A target for a PLACE (or one person) for a quarter or the year.  Fill "fixed achieved" only for a finished quarter."""
    list_display = ("who", "label", "start_date", "end_date", "amount", "fixed_achieved")
    list_filter = ("place", "user")
    date_hierarchy = "start_date"


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "phone", "priority", "need", "entered_by", "assigned_to", "assigned_to2", "done", "created_at")
    list_filter = ("priority", "need", "done")
    search_fields = ("customer_name", "phone")


admin.site.register(SiteDetails)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    """The projects of the payment sheet.  Change "received" here as customers pay."""
    list_display = ("project_id", "customer", "region", "sales_name", "net_value", "received", "balance")
    list_filter = ("region", "sales_name")
    search_fields = ("customer", "project_id")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("collection", "amount", "date", "stage", "entered_by", "created_at")
    list_filter = ("stage", "entered_by")
    date_hierarchy = "date"
