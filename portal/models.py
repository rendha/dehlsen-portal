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
    map_link = models.CharField("Google Maps location", max_length=500, blank=True, help_text="A Google Maps link, or latitude,longitude, or an address (optional)")
    site_visit_by = models.DateField("site visit by", null=True, blank=True, help_text="The date the site visit must be done by (optional)")
    quotation_by = models.DateField("quotation by", null=True, blank=True, help_text="The date the quotation must be given by (optional)")
    lead_no = models.CharField("lead ID", max_length=20, blank=True, db_index=True, help_text="Filled automatically, e.g. L26-27/0012")

    class Meta:
        ordering = ["done", "-created_at"]

    @staticmethod
    def make_lead_no(when=None):
        """The next lead ID of the financial year (April-March): L26-27/0001, L26-27/0002 ..."""
        when = timezone.localtime(when).date() if when else timezone.localdate()
        year = when.year if when.month >= 4 else when.year - 1
        head = "L%02d-%02d/" % (year % 100, (year + 1) % 100)
        last = 0
        for no in Lead.objects.filter(lead_no__startswith=head).values_list("lead_no", flat=True):
            try:
                last = max(last, int(no.rsplit("/", 1)[1]))
            except ValueError:
                pass
        return "%s%04d" % (head, last + 1)

    def save(self, *args, **kwargs):
        if not self.lead_no:
            self.lead_no = Lead.make_lead_no(self.created_at if self.pk is None else None)
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(kwargs["update_fields"]) + ["lead_no"]
        super().save(*args, **kwargs)

    @property
    def map_url(self):
        """A safe address to open in Google Maps ('' when none was given).  A plain address or 'lat,lng' becomes a Maps search."""
        t = (self.map_link or "").strip()
        if not t:
            return ""
        if t.lower().startswith(("http://", "https://")):
            return t
        from urllib.parse import quote
        return "https://www.google.com/maps/search/?api=1&query=" + quote(t)

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


class Collection(models.Model):
    """One sold project and how much of its price has been collected.  Loaded from the payment sheet (import_collections), then edited in Admin."""
    project_id = models.CharField(max_length=30, unique=True)
    booking_date = models.DateField(null=True, blank=True)
    customer = models.CharField(max_length=150)
    region = models.CharField(max_length=60, blank=True)
    sales_name = models.CharField(max_length=60, help_text="The sales person, as named in the sheet (Huda, Fouzan ...).")
    kw = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    net_value = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Deal value minus discount (Rs).")
    received = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Total collected so far (Rs).")
    deal_value = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Deal value before discount (Rs).")
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_gp = models.DecimalField("expected gross profit", max_digits=14, decimal_places=2, default=0)
    incentive_category = models.CharField(max_length=5, blank=True)
    site_address = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    segment = models.CharField(max_length=20, blank=True)
    system_type = models.CharField(max_length=20, blank=True)
    almm = models.CharField("DCR / NDCR", max_length=10, blank=True)
    panel = models.CharField(max_length=60, blank=True)
    inverter = models.CharField(max_length=60, blank=True)
    work_status = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    quotation_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="The confirmed quotation this came from (filled automatically).")

    class Meta:
        ordering = ["-booking_date", "project_id"]

    @property
    def balance(self):
        return self.net_value - self.received

    def __str__(self):
        return "%s %s" % (self.project_id, self.customer)


class Payment(models.Model):
    """One payment received from a customer.  Added by the sales person of that customer (or a director); adds to Collection.received."""
    STAGES = [("advance", "Advance"), ("material", "Material dispatch"), ("installation", "Installation"), ("handover", "Handover"), ("other", "Other")]
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField(null=True, blank=True, help_text="Empty for old payments whose date the sheet did not have.")
    stage = models.CharField(max_length=15, choices=STAGES, default="other")
    note = models.CharField(max_length=200, blank=True)
    from_sheet = models.BooleanField(default=False)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed = models.BooleanField(default=True, help_text="A payment typed by a sales person waits here until Accounts confirms it with the bank. Only confirmed payments count in Collection.received.")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirmed_on = models.DateField(null=True, blank=True)
    bank_checked = models.BooleanField(default=False, help_text="Accounts ticks this once the money is seen in the bank statement.")
    bank_checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    bank_checked_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return "%s %s" % (self.collection.project_id, self.amount)


class ProjectWork(models.Model):
    """Where one customer's installation work stands: the stage ticks, feasibility, commissioning and handover.  Ticked by the project people."""
    STAGES = [("site_estimation", "Site estimation"), ("design", "Design"), ("bos", "BOS"), ("inverter_done", "Inverter"), ("panel_done", "Panel"),
              ("electrical", "Electrical work"), ("structure", "Structure work"), ("inv_program", "Inverter programming"), ("testing", "Testing"), ("meter_fix", "Meter fix")]
    FEASIBILITY = [("", "Not checked"), ("ok", "Feasible"), ("issue", "Feasibility issue")]

    name = models.CharField(max_length=200)
    name_key = models.CharField(max_length=200, db_index=True, blank=True)
    project_id = models.CharField(max_length=30, blank=True)
    collection = models.ForeignKey("portal.Collection", null=True, blank=True, on_delete=models.SET_NULL, related_name="works")
    kw = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=150, blank=True)
    site_address = models.TextField(blank=True)
    map_link = models.CharField(max_length=500, blank=True)
    system = models.CharField(max_length=40, blank=True)
    panel_make = models.CharField(max_length=60, blank=True)
    inverter_make = models.CharField(max_length=60, blank=True)
    booking_date = models.DateField(null=True, blank=True)

    site_estimation = models.BooleanField(default=False)
    design = models.BooleanField(default=False)
    bos = models.BooleanField("BOS", default=False)
    inverter_done = models.BooleanField("inverter", default=False)
    panel_done = models.BooleanField("panel", default=False)
    electrical = models.BooleanField("electrical work", default=False)
    structure = models.BooleanField("structure work", default=False)
    inv_program = models.BooleanField("inverter programming", default=False)
    testing = models.BooleanField(default=False)
    meter_fix = models.BooleanField(default=False)

    wifi = models.BooleanField("Wi-Fi connected", null=True, blank=True)
    work_status = models.CharField(max_length=300, blank=True, help_text="What is holding it / where it is, e.g. waiting for documentation")
    commission_date = models.DateField(null=True, blank=True)
    handover = models.BooleanField("documents handed over", default=False)
    handover_note = models.CharField(max_length=200, blank=True)
    feasibility = models.CharField(max_length=10, choices=FEASIBILITY, blank=True, default="")
    feasibility_note = models.CharField(max_length=300, blank=True)
    estimator = models.CharField(max_length=60, blank=True)
    structure_estimation = models.CharField(max_length=60, blank=True)
    material_dispatched = models.BooleanField(null=True, blank=True)
    remarks = models.CharField(max_length=300, blank=True)

    # how the customer pays: cash, or a bank loan that the bank pays in two stages (the first only after sanction; work starts after it)
    CASH, LOAN = "cash", "loan"
    PAYMENT_MODES = [(CASH, "Own money / cash"), (LOAN, "Bank loan")]
    payment_mode = models.CharField(max_length=5, choices=PAYMENT_MODES, default=CASH)
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Total the bank gives, e.g. 200000")
    bank1_amount = models.DecimalField("bank stage 1 amount", max_digits=12, decimal_places=2, default=140000, help_text="Paid after sanction, before work starts")
    loan_sanctioned_on = models.DateField(null=True, blank=True)
    bank1_received_on = models.DateField(null=True, blank=True)
    bank2_received_on = models.DateField(null=True, blank=True)

    # KSEB / PM Surya Ghar clocks and warranty
    feasibility_date = models.DateField(null=True, blank=True)
    registration_paid = models.BooleanField("KSEB registration fee paid", default=False)
    handover_date = models.DateField(null=True, blank=True)

    # the 12 KSEB / PM Surya Ghar steps (dates by step key; feasibility and commissioning use the fields above)
    KSEB_STEPS = [("portal_app", "1 Portal application"), ("docs", "2 KSEB documents"), ("feasibility", "3 Feasibility"), ("reg_paid", "4 Registration fee paid"),
                  ("work_start", "5 Work start"), ("work_done", "6 Work completion"), ("netmeter_app", "7 Net meter application"), ("inspection", "8 Inspection"),
                  ("meter_fix", "9 Net meter fix"), ("programming", "10 Programming"), ("commissioning", "11 Commissioning certificate"), ("subsidy", "12 Subsidy credited")]
    sales_person = models.CharField(max_length=60, blank=True, help_text="Whose customer this is")
    quotation_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="The confirmed quotation of this customer (filled automatically)")
    engineer = models.CharField("site in-charge / engineer", max_length=60, blank=True)
    kseb = models.JSONField(default=dict, blank=True)
    track_token = models.CharField(max_length=40, blank=True, db_index=True, help_text="The private link the customer opens to see the schedule (made when first needed)")
    customer_plan = models.JSONField(default=dict, blank=True, help_text="Planned dates shown to the customer, by step key")
    kseb_consumer_no = models.CharField(max_length=30, blank=True)
    arn = models.CharField("PM Surya Ghar application no.", max_length=40, blank=True)
    scheme = models.CharField(max_length=40, blank=True)

    # equipment serial numbers
    panel_count = models.PositiveIntegerField(null=True, blank=True)
    panel_serials = models.TextField(blank=True, help_text="All panel serial numbers, separated by commas")
    inverter_serial = models.CharField(max_length=60, blank=True)
    energy_meter_serial = models.CharField(max_length=60, blank=True)
    net_meter_serial = models.CharField(max_length=60, blank=True)

    # customer and system details from the Project Master workbook
    email = models.CharField(max_length=100, blank=True)
    alt_phone = models.CharField("alternate phone", max_length=40, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    district = models.CharField(max_length=40, blank=True)
    region = models.CharField(max_length=30, blank=True)
    segment = models.CharField(max_length=30, blank=True)
    load_change = models.CharField("load change required", max_length=20, blank=True)
    name_change = models.CharField("name change required", max_length=20, blank=True, help_text="Required / Done (empty = not needed)")
    almm = models.CharField("ALMM (DCR / NDCR)", max_length=10, blank=True)
    project_stage = models.CharField(max_length=40, blank=True, help_text="Stage from the Project Master (the ticks decide it once work is ticked)")
    quote_value = models.DecimalField("quote value (from the master sheet)", max_digits=12, decimal_places=2, null=True, blank=True)
    panel_wp = models.DecimalField("panel wattage (Wp)", max_digits=7, decimal_places=1, null=True, blank=True)
    dc_kwp = models.DecimalField("DC capacity (kWp)", max_digits=8, decimal_places=2, null=True, blank=True)
    ac_kw = models.DecimalField("AC / inverter capacity (kW)", max_digits=8, decimal_places=2, null=True, blank=True)
    inverter_phase = models.CharField(max_length=10, blank=True)
    inverter_model = models.CharField(max_length=60, blank=True)
    roof_type = models.CharField(max_length=30, blank=True)
    panel_at_site = models.BooleanField("panel material at site", null=True, blank=True)
    inverter_at_site = models.BooleanField("inverter material at site", null=True, blank=True)
    energy_meter_make = models.CharField(max_length=40, blank=True)
    net_meter_make = models.CharField(max_length=40, blank=True)
    kseb_ref = models.CharField("KSEB application / ref. no.", max_length=40, blank=True)
    docs_status = models.CharField("KSEB documents status", max_length=30, blank=True)
    reg_receipt = models.CharField("registration fee receipt no.", max_length=40, blank=True)
    inspection_status = models.CharField(max_length=30, blank=True)
    subsidy_status = models.CharField(max_length=30, blank=True)
    bank_details = models.CharField("bank details submitted on portal", max_length=10, blank=True)
    programming_notes = models.TextField(blank=True)
    kseb_notes = models.TextField("blocker / notes", blank=True)
    handover_status = models.CharField(max_length=20, blank=True)
    handover_mode = models.CharField(max_length=20, blank=True)
    handed_over_by = models.CharField(max_length=60, blank=True)
    docs_given = models.JSONField("documents given to the customer", default=dict, blank=True)
    invoice_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    warranty_start = models.DateField(null=True, blank=True)
    panel_perf_yrs = models.PositiveSmallIntegerField("panel performance warranty (yrs)", null=True, blank=True)

    # contractor labour
    electrical_contractor = models.CharField(max_length=60, blank=True)
    electrical_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    electrical_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    structure_contractor = models.CharField(max_length=60, blank=True)
    structure_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    structure_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # invoice and warranty
    invoice_no = models.CharField(max_length=40, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    panel_warranty_yrs = models.PositiveSmallIntegerField(null=True, blank=True)
    inverter_warranty_yrs = models.PositiveSmallIntegerField(null=True, blank=True)
    workmanship_yrs = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = 5 years")

    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def ticks(self):
        return [(key, label, getattr(self, key)) for key, label in self.STAGES]

    @property
    def done_count(self):
        return sum(1 for _k, _l, v in self.ticks if v)

    @property
    def progress(self):
        return int(round(self.done_count * 100 / len(self.STAGES)))

    @property
    def is_loan(self):
        return self.payment_mode == self.LOAN

    @property
    def bank2_amount(self):
        return max(0, (self.loan_amount or 0) - (self.bank1_amount or 0))

    @property
    def commissioned(self):
        return bool(self.commission_date) or (self.testing and self.meter_fix)

    @property
    def map_url(self):
        t = (self.map_link or "").strip()
        if not t:
            return ""
        if t.lower().startswith(("http://", "https://")):
            return t
        from urllib.parse import quote
        return "https://www.google.com/maps/search/?api=1&query=" + quote(t)


class CrewAssignment(models.Model):
    """Who goes to which site on which day (the list Riswan used to send on WhatsApp): an electrical or structure team, a site, a date."""
    WORKS = [("Electrical", "Electrical"), ("Structure", "Structure"), ("Panel fixing", "Panel fixing"), ("Inverter", "Inverter"),
             ("Earthing / civil", "Earthing / civil"), ("Testing", "Testing"), ("Site visit / survey", "Site visit / survey"),
             ("Material delivery", "Material delivery"), ("Other", "Other")]
    STATUS = [("planned", "Planned"), ("done", "Done"), ("cancelled", "Cancelled")]

    date = models.DateField(db_index=True)
    team = models.CharField(max_length=200, help_text="Contractor or worker names")
    work = models.CharField(max_length=30, choices=WORKS, default="Electrical")
    project = models.ForeignKey("portal.ProjectWork", null=True, blank=True, on_delete=models.SET_NULL, related_name="crew_visits")
    site = models.CharField(max_length=200, blank=True, help_text="Site typed by hand when it is not a project")
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="planned")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "work", "team", "id"]

    def __str__(self):
        return f"{self.date} {self.team} - {self.site_name}"

    @property
    def site_name(self):
        return self.project.name if self.project_id else self.site



class Meeting(models.Model):
    """A scheduled meeting and its minutes: who attends, what was discussed and decided, and the action items to be checked later."""
    STATUS = [("scheduled", "Scheduled"), ("held", "Held"), ("cancelled", "Cancelled")]

    title = models.CharField(max_length=200)
    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True)
    objective = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="scheduled")
    conducted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="The person who conducts the meeting and keeps its minutes")
    follow_up_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="follow_ups",
                                     help_text="The earlier meeting whose unfinished items are checked in this one")
    prepared_by = models.CharField(max_length=120, blank=True)
    approved_by = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return "%s (%s)" % (self.title, self.date)

    def can_edit(self, user):
        return bool(getattr(user, "is_superuser", False) or (self.conducted_by_id and self.conducted_by_id == user.id)
                    or (self.created_by_id and self.created_by_id == user.id))


class MeetingAttendee(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendees")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=120, blank=True, help_text="For people without a portal login")
    present = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.label

    @property
    def label(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return self.name


class MeetingPoint(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="points")
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True, help_text="What was discussed and decided")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


class MeetingAction(models.Model):
    """One thing said in a meeting that somebody has to do, with a date, so that it can be checked later."""
    STATUS = [("open", "Open"), ("progress", "In progress"), ("done", "Done"), ("dropped", "Dropped")]

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="actions")
    point = models.ForeignKey(MeetingPoint, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions")
    text = models.CharField(max_length=500)
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="meeting_actions")
    owner_name = models.CharField(max_length=120, blank=True, help_text="For people without a portal login")
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    done_on = models.DateField(null=True, blank=True)
    remark = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text

    @property
    def owner_label(self):
        if self.owner_user_id:
            return self.owner_user.get_full_name() or self.owner_user.get_username()
        return self.owner_name

    @property
    def is_open(self):
        return self.status in ("open", "progress")

    @property
    def overdue(self):
        return bool(self.is_open and self.target_date and self.target_date < timezone.localdate())

class BankLoan(models.Model):
    """A customer who wants a bank loan: the lead waits here (not yet a project) until the bank sanctions it.
    Sanctioned -> the lead is marked Won and the loan details go to the project.  Rejected -> own money / another bank, or the lead is Lost."""
    DOCS, APPLIED, QUERY, SANCTIONED, REJECTED, CASH, LOST = "docs", "applied", "query", "sanctioned", "rejected", "cash", "lost"
    STATUS = [(DOCS, "Documents being collected"), (APPLIED, "Applied"), (QUERY, "Query from bank"), (SANCTIONED, "Sanctioned"),
              (REJECTED, "Rejected - decide"), (CASH, "Switched to own money"), (LOST, "Lost (loan rejected)")]
    ACTIVE = (DOCS, APPLIED, QUERY, REJECTED)
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="loan")
    bank = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField("loan amount applied for", max_digits=12, decimal_places=2, default=0)
    applied_on = models.DateField(null=True, blank=True)
    expected_on = models.DateField("expected sanction date", null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default=DOCS)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="loans_followed")
    notes = models.TextField(blank=True)
    reject_reason = models.CharField(max_length=200, blank=True)
    sanctioned_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return "Loan of %s (%s)" % (self.lead, self.get_status_display())

    @property
    def active(self):
        return self.status in self.ACTIVE

    @property
    def waiting_days(self):
        d = self.applied_on or self.created_at.date()
        return (timezone.localdate() - d).days
