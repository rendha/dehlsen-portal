from django.conf import settings
from django.db import models
from django.utils import timezone


class Place(models.Model):
    """A sales area (Kochi, Kannur, Kozhikode and others).  Targets can be set for a place; its people's confirmed customers are added together."""
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Extra details of a person: the WhatsApp number a task message is sent to."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portal_profile")
    whatsapp = models.CharField("WhatsApp number", max_length=30, blank=True, help_text="With country code, e.g. 919876543210 (a 10-digit number is taken as Indian).")

    sales_name = models.CharField("name in 'Quotation For'", max_length=100, blank=True,
                                  help_text="Sales persons only: the name he types in the Quotation For box, if it differs from his first name / username.")

    place = models.ForeignKey("Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="members", help_text="The sales area of this person.")
    director = models.BooleanField(default=False, help_text="Directors see the sales dashboard (everyone's targets) even without a target of their own.")

    def __str__(self):
        return "%s (%s)" % (self.user, self.whatsapp or "no WhatsApp number")


class TaskType(models.Model):
    """A kind of task, and the people who do it.  When someone gives this task, only these people are shown."""
    name = models.CharField(max_length=100, unique=True)
    people = models.ManyToManyField(settings.AUTH_USER_MODEL, through="TaskPerson", blank=True, related_name="task_types",
                                    help_text="The people who do this task")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TaskPerson(models.Model):
    """One person who does a task.  The note is shown next to the name, e.g. the area for Leads ("Ernakulam")."""
    task_type = models.ForeignKey(TaskType, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_assignments")
    note = models.CharField(max_length=100, blank=True, help_text="Shown next to the name, e.g. the area")

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["task_type", "user"], name="unique_task_person")]

    def __str__(self):
        return "%s - %s%s" % (self.task_type, self.user, (" (%s)" % self.note) if self.note else "")


class Task(models.Model):
    task_type = models.ForeignKey(TaskType, on_delete=models.PROTECT, related_name="tasks")
    details = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="tasks_given")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks_received")
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    due_time = models.TimeField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "due_time", "id"]

    def __str__(self):
        return "%s -> %s (%s)" % (self.task_type, self.assigned_to, self.due_date)

    @property
    def overdue(self):
        return not self.done and self.due_date < timezone.localdate()

    def days_left(self):
        return (self.due_date - timezone.localdate()).days

    def due_text(self):
        """'Sat 7 Nov, 11:00' """
        text = "%s %d %s" % (self.due_date.strftime("%a"), self.due_date.day, self.due_date.strftime("%b"))
        if self.due_time:
            text += ", " + self.due_time.strftime("%H:%M")
        return text

    def left_text(self):
        """'due in 4 days', 'due today', '2 days overdue', 'done' """
        if self.done:
            return "done"
        n = self.days_left()
        if n == 0:
            return "due today"
        if n == 1:
            return "due tomorrow"
        if n > 1:
            return "due in %d days" % n
        return "%d day%s overdue" % (-n, "" if n == -1 else "s")


class PushSubscription(models.Model):
    """A phone / browser that agreed to get alerts."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "%s: %s" % (self.user, self.endpoint[:40])


class SalesTarget(models.Model):
    """A target in rupees for a PLACE (or for one person) for a period: a quarter, or the year (a period longer than ~4 months).
    Achieved = the final price of the confirmed customers (one per client) dated inside the period, unless "fixed achieved" is filled
    (for a finished quarter whose result is already known)."""
    place = models.ForeignKey(Place, null=True, blank=True, on_delete=models.CASCADE, related_name="targets")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="sales_targets",
                             help_text="Fill the place OR the person, not both.")
    label = models.CharField(max_length=60, blank=True, help_text="e.g. Q3 or Year")
    start_date = models.DateField()
    end_date = models.DateField()
    amount = models.DecimalField("target (Rs)", max_digits=14, decimal_places=2)
    fixed_achieved = models.DecimalField("fixed achieved (Rs)", max_digits=14, decimal_places=2, null=True, blank=True,
                                         help_text="Leave empty to count it from the confirmed customers. Fill it for a finished quarter.")

    class Meta:
        ordering = ["-end_date", "place__name", "user__username"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.place_id) == bool(self.user_id):
            raise ValidationError("Fill either the place or the person (one of them).")

    @property
    def who(self):
        return self.place.name if self.place_id else (self.user.get_full_name() or self.user.get_username())

    def __str__(self):
        return "%s %s: %s (%s to %s)" % (self.who, self.label, self.amount, self.start_date, self.end_date)


class Lead(models.Model):
    """A customer lead somebody enters and gives to a person to call or visit.  Priority: Hot is the highest."""
    COLD, MEDIUM, HOT = "cold", "medium", "hot"
    PRIORITY_CHOICES = [(HOT, "Hot"), (MEDIUM, "Medium"), (COLD, "Cold")]
    CALL, VISIT = "call", "visit"
    BOTH = "both"
    NEED_CHOICES = [(CALL, "Call"), (VISIT, "Site visit"), (BOTH, "Call + Site visit")]

    customer_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    area = models.CharField("place", max_length=100, blank=True)
    need = models.CharField(max_length=60, default=CALL, help_text="call, visit, other - separated by commas")
    need_other = models.CharField("what to do (other)", max_length=200, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM)
    note = models.TextField(blank=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leads_entered")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads_assigned")
    assigned_to2 = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads_assigned2")
    quotation_id = models.PositiveIntegerField(null=True, blank=True, help_text="The quotation made for this lead (the latest one is shown)")
    next_step = models.CharField(max_length=100, blank=True, help_text="What has to happen next, e.g. Site visit")
    lost = models.BooleanField(default=False)
    lost_reason = models.CharField(max_length=100, blank=True)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    CUSTOMER_TYPES = [("residential", "Residential"), ("commercial", "Commercial"), ("industrial", "Industrial")]
    DCR_CHOICES = [("dcr", "DCR"), ("non_dcr", "Non-DCR"), ("undecided", "DCR / Non-DCR not decided")]
    SYSTEM_TYPES = [("on_grid", "On-grid"), ("off_grid", "Off-grid"), ("hybrid", "Hybrid"), ("other", "Other")]
    customer_type = models.CharField(max_length=15, choices=CUSTOMER_TYPES, blank=True)
    dcr_choice = models.CharField(max_length=10, choices=DCR_CHOICES, blank=True, help_text="Only for residential leads")
    system_type = models.CharField(max_length=10, choices=SYSTEM_TYPES, blank=True)
    system_other = models.CharField("system type (other)", max_length=100, blank=True)

    class Meta:
        ordering = ["done", "-created_at"]

    @property
    def system_label(self):
        if self.system_type == "other":
            return self.system_other or "Other"
        return self.get_system_type_display() if self.system_type else ""

    @property
    def type_chips(self):
        """Short labels shown on the lead card: Residential, DCR, On-grid ..."""
        out = []
        if self.customer_type:
            out.append(self.get_customer_type_display())
            if self.customer_type == "residential" and self.dcr_choice:
                out.append({"dcr": "DCR", "non_dcr": "Non-DCR", "undecided": "DCR/Non-DCR undecided"}[self.dcr_choice])
        if self.system_type:
            out.append(self.system_label)
        return out

    @property
    def need_list(self):
        """What has to be done, as a list of words: ['Call', 'Site visit', 'Fix the meter'] (older leads saved 'both')."""
        parts = []
        for key in (self.need or "").replace("both", "call,visit").split(","):
            key = key.strip()
            if key == "call":
                parts.append("Call")
            elif key == "visit":
                parts.append("Site visit")
            elif key == "other":
                parts.append(self.need_other or "Other")
        return parts or ["Quotation first"]

    def __str__(self):
        return "%s (%s)" % (self.customer_name, self.get_priority_display())


class LeadEvent(models.Model):
    """One line in the history of a lead: who did what and when (a call, a site visit, a quotation, handing it to someone, won, lost)."""
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="events")
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=20, blank=True)
    text = models.CharField(max_length=400)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return "%s: %s" % (self.lead, self.text)


class SiteDetails(models.Model):
    """What the person saw at the site visit: needed before the quotation is finalised and before the lead can be Won."""
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="site")
    roof_length = models.CharField("roof length", max_length=60, blank=True)
    roof_width = models.CharField("roof width", max_length=60, blank=True)
    roof_layout = models.TextField("roof / plant layout", blank=True)
    inverter_position = models.CharField(max_length=200, blank=True)
    acdb_position = models.CharField("ACDB position", max_length=200, blank=True)
    dcdb_position = models.CharField("DCDB position", max_length=200, blank=True)
    earth_rod_position = models.CharField(max_length=200, blank=True)
    cable_laying = models.TextField("cable laying", blank=True)
    meter_position = models.CharField(max_length=200, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return "Site details of %s" % self.lead


class SitePhoto(models.Model):
    """A roof photo / layout sketch.  Kept inside the database (shrunk on the phone first) so it works on any hosting."""
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="photos")
    data = models.BinaryField()
    content_type = models.CharField(max_length=60, default="image/jpeg")
    caption = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
