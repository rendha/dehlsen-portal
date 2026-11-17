"""Compares the store's search list (store/catalog.json) with the Sales app's rate list (Admin > Products and Panel options), item by item.
    python manage.py compare_rates
Prints: same rate, DIFFERENT rate, only in the store list, only in the Sales app.  Nothing is changed."""
import json
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand

from quotations.models import PanelOption, Product


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def money(v):
    return "{:,.2f}".format(Decimal(str(v)))


class Command(BaseCommand):
    help = "Compare the store rate list with the Sales app rate list."

    def handle(self, *args, **opts):
        out = self.stdout.write
        cat = json.load(open(Path(__file__).resolve().parents[2] / "catalog.json", encoding="utf-8"))
        prods = list(Product.objects.filter(is_active=True))
        by = {}
        for p in prods:
            by[norm(p.name)] = p
            by[norm(p.make + p.name)] = p
            by[norm(p.name + p.make)] = p
        out("Store list: %d items.  Sales app: %d products, %d panel options.\n" % (len(cat), len(prods), PanelOption.objects.filter(is_active=True).count()))
        same, diff, store_only, used = [], [], [], set()
        for it in cat:
            if it["group"] == "Solar panels":
                continue
            p = next((by[k] for k in (norm(it["name"]), norm(it["make"] + it["name"]), norm(it["name"] + it["make"])) if k in by), None)
            if p is None:
                store_only.append(it)
                continue
            used.add(p.pk)
            (same if Decimal(str(it["rate"])) == Decimal(str(p.rate)) else diff).append((it, p))
        # panels: the store lists a price per panel, the Sales app a rate per watt
        options = list(PanelOption.objects.filter(is_active=True))
        p_same, p_diff, p_store_only, p_used = [], [], [], set()
        for it in [c for c in cat if c["group"] == "Solar panels"]:
            m = re.match(r"\s*(\w+)\s+(\w+)\s+(\d+)\s*W", it["name"], re.I)
            opt = None
            if m:
                opt = next((o for o in options if m.group(1).lower() in o.company.lower() and m.group(2).lower() in o.panel_type.lower()
                            and int(o.wattage) == int(m.group(3))), None)
            if opt is None:
                p_store_only.append(it)
                continue
            p_used.add(opt.pk)
            per_panel = Decimal(str(opt.rate_per_watt)) * Decimal(str(opt.wattage))
            (p_same if abs(per_panel - Decimal(str(it["rate"]))) < Decimal("0.5") else p_diff).append((it, opt, per_panel))

        out("== DIFFERENT RATE (%d) ==" % (len(diff) + len(p_diff)))
        for it, p in diff:
            out("  %-48s store %10s   sales %10s" % ((it["name"] + " " + it["make"]).strip()[:48], money(it["rate"]), money(p.rate)))
        for it, o, per in p_diff:
            out("  %-48s store %10s   sales %10s  (%s per watt x %s W)" % (it["name"], money(it["rate"]), money(per), money(o.rate_per_watt), o.wattage))
        out("\n== SAME RATE (%d) ==" % (len(same) + len(p_same)))
        for it, p in same:
            out("  %s  %s" % ((it["name"] + " " + it["make"]).strip()[:48], money(it["rate"])))
        for it, o, per in p_same:
            out("  %s  %s" % (it["name"], money(it["rate"])))
        out("\n== ONLY IN THE STORE LIST (%d): the Sales app has no such item ==" % (len(store_only) + len(p_store_only)))
        for it in store_only + p_store_only:
            out("  [%s] %s %s  %s" % (it["group"], it["name"], it["make"], money(it["rate"])))
        out("\n== ONLY IN THE SALES APP (%d): the store list has no such item ==" % (len([p for p in prods if p.pk not in used]) + len([o for o in options if o.pk not in p_used])))
        for p in prods:
            if p.pk not in used:
                out("  [%s] %s  %s" % (p.category, p.name, money(p.rate)))
        for o in options:
            if o.pk not in p_used:
                out("  [panel] %s %s %s W  %s per watt = %s per panel" % (o.company, o.panel_type, o.wattage, money(o.rate_per_watt), money(Decimal(str(o.rate_per_watt)) * Decimal(str(o.wattage)))))
