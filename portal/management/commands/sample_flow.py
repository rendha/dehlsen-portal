"""py manage.py sample_flow           -  makes ONE sample customer and shows how the details travel: Lead -> quotation -> Won -> Project -> Collections.
py manage.py sample_flow --remove  -  deletes every sample record again.

Run it on your PC's own test database only (close the window that has DATABASE_URL set).  Every sample record is called SAMPLE.
It prints, step by step, what appeared in which part of the portal, and which details are copied once and which stay linked."""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.utils import timezone

from portal.models import Collection, Lead, LeadEvent, Payment, ProjectWork, SiteDetails
from portal.project_sync import ensure_projects
from quotations.models import Quotation

NAME, OFFER, PID = "SAMPLE Anil Kumar", "SAMPLE-0001", "SAMPLE-001"


def blank_quotation(**given):
    """A Quotation with every required field that has no default set to a neutral value, so this works whatever the model looks like."""
    vals = {}
    for f in Quotation._meta.concrete_fields:
        if f.primary_key or f.name in given or f.null or f.has_default() or f.blank and f.empty_strings_allowed:
            continue
        if isinstance(f, models.ForeignKey):
            continue
        if isinstance(f, models.DecimalField):
            vals[f.name] = Decimal("0")
        elif isinstance(f, (models.IntegerField,)):
            vals[f.name] = 0
        elif isinstance(f, models.BooleanField):
            vals[f.name] = False
        elif isinstance(f, models.DateTimeField):
            vals[f.name] = timezone.now()
        elif isinstance(f, models.DateField):
            vals[f.name] = datetime.date.today()
        else:
            vals[f.name] = ""
    vals.update(given)
    return Quotation.objects.create(**vals)


def remove(say):
    ProjectWork.objects.filter(name__startswith="SAMPLE").delete()
    Collection.objects.filter(project_id=PID).delete()
    Lead.objects.filter(customer_name__startswith="SAMPLE").delete()
    Quotation.objects.filter(offer_no=OFFER).delete()
    say("Sample records removed.")


class Command(BaseCommand):
    help = "Create one sample customer and show how its details travel through the portal."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **o):
        say = self.stdout.write
        if o["remove"]:
            return remove(say)
        if Lead.objects.filter(customer_name__startswith="SAMPLE").exists() or Quotation.objects.filter(offer_no=OFFER).exists():
            raise CommandError("A sample already exists. Run  python manage.py sample_flow --remove  first.")
        user = get_user_model().objects.filter(is_superuser=True).first() or get_user_model().objects.first()
        if user is None:
            raise CommandError("There is no user in this database. Create one first (createsuperuser).")

        say("\nSTEP 1  A lead is entered (Leads)")
        lead = Lead.objects.create(customer_name=NAME, phone="9000000001", area="Kozhikode", entered_by=user, assigned_to=user,
                                   note="Sample lead made by sample_flow", next_step="Site visit")
        LeadEvent.objects.create(lead=lead, by=user, kind="note", text="Sample lead entered")
        say("   Lead #%d  %s  | phone %s | place %s | owner %s" % (lead.pk, lead.customer_name, lead.phone, lead.area, user))

        say("\nSTEP 2  Site visit done: site details saved (they are needed before the lead can be Won)")
        SiteDetails.objects.create(lead=lead, roof_length="40 ft", roof_width="25 ft", roof_layout="Flat RCC roof, no shadow",
                                   inverter_position="Near the main board", meter_position="Gate pillar", updated_by=user)
        LeadEvent.objects.create(lead=lead, by=user, kind="site", text="Site details saved (sample)")
        say("   Roof 40 x 25 ft, inverter and meter positions saved on the lead.")

        say("\nSTEP 3  A quotation is made in Sales for this customer")
        q = blank_quotation(offer_no=OFFER, business_name=NAME, customer_name="Sample Sales", phone="9000000001", location="Kozhikode",
                            address="Sample House, Kozhikode", date=datetime.date.today(), system_size=Decimal("5"), final_quotation_price=Decimal("330000"),
                            capacity="5", category="Residential")
        lead.quotation_id = q.pk
        lead.save(update_fields=["quotation_id"])
        say("   Quotation %s  Rs %s  (the lead now shows this quotation)" % (q.offer_no, q.final_quotation_price))

        say("\nSTEP 4  The customer says yes: lead marked WON")
        Quotation.objects.filter(pk=q.pk).update(counted=True, is_customer=True)
        col = Collection.objects.create(project_id=PID, customer=NAME, sales_name="Sample Sales", kw=Decimal("5"), deal_value=Decimal("330000"),
                                        discount=Decimal("0"), net_value=Decimal("330000"), received=Decimal("100000"), quotation_id=q.pk,
                                        booking_date=datetime.date.today(), phone="9000000001")
        Payment.objects.create(collection=col, amount=Decimal("100000"), date=datetime.date.today(), stage="advance", note="Sample advance", entered_by=user)
        ensure_projects(quotation_ids=[q.pk])                 # exactly what the real Won button calls
        LeadEvent.objects.create(lead=lead, by=user, kind="won", text="marked the lead WON - the customer said yes")
        w = ProjectWork.objects.filter(quotation_id=q.pk).first()
        if w is None:
            raise CommandError("The project was not created. Tell me what you saw above.")
        say("   Project created by itself:  %s  (project id %s)" % (w.name, w.project_id))
        say("   Copied into the project from the quotation:")
        for label, v in (("phone", w.phone), ("site address", w.site_address), ("location", w.location), ("kW", w.kw), ("sales person", w.sales_person),
                         ("booking date", w.booking_date), ("system", w.system)):
            say("      %-13s %s" % (label, v or "-"))
        say("   Linked to the money sheet (Collections): %s, agreed Rs %s, received Rs %s" % (w.collection.project_id if w.collection_id else "NOT LINKED",
                                                                                  col.net_value, col.received))

        say("\nSTEP 5  Now change things in ONE place and see what follows")
        lead.phone = "9111111111"
        lead.save(update_fields=["phone"])
        w.refresh_from_db()
        say("   Lead phone changed to 9111111111.  Project phone is now: %s   -> %s" % (w.phone, "NOT updated (copied once, when the project was made)" if w.phone != lead.phone else "updated"))
        Payment.objects.create(collection=col, amount=Decimal("50000"), date=datetime.date.today(), stage="material", note="Sample second payment", entered_by=user)
        col.received = Decimal("150000")
        col.save(update_fields=["received"])
        w.refresh_from_db()
        say("   Second payment of Rs 50,000 added in Collections.  The project reads the money from there, so it now shows received Rs %s of Rs %s   -> updated (live link)"
            % (w.collection.received, w.collection.net_value))

        say("\nWHERE TO LOOK  (start the server:  python manage.py runserver)")
        say("   Leads            /leads/                 the SAMPLE lead with its history, site details and quotation")
        say("   Project progress /progress/              the SAMPLE project with its steps, phone, address, kW and the money")
        say("   Collections      /collections/           SAMPLE-001 with two payments")
        say("   Delete the sample afterwards:  python manage.py sample_flow --remove")
