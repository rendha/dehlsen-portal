"""py manage.py relink_payments [--dry-run] [--unlink]  -  links every project to the payment row of the SAME customer.

The payment sheet numbers some customers differently from the Project Master (RAYEESUDHEEN is 157 there, 160 in the master; PRAMOD KUMAR 160 there, 152 in the master),
so a project was linked to another customer's payment row: it showed that name, deal value, received and balance.
  MOVE    a project linked to another customer's payment row goes to the payment row of its own name (only when that row is free)
  LINK    a payment row that has no project is linked to the one project of that name (a project that has no payment row)
  CHECK   a project linked to a payment row of another name and no payment row of its own: listed only; with --unlink the wrong link is taken off
A shortened name is the same customer (ABDUSSAREEF KORALIYADAN = ABDUSSAREEF, A T THOMAS = THOMAS AT).  The Project Master workbook is the MAIN list: after linking, every payment row takes the project number of its project (RAYEESUDHEEN 157 -> 160, PRAMOD KUMAR 160 -> 152),
so the two lists use the same numbers.  Payment amounts are never edited.  A number that another, unmatched payment row already holds is left and listed."""
import re
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.db import transaction

from portal.models import Collection, ProjectWork


def toks(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def same(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    ja, jb = "".join(ta), "".join(tb)
    if ja == jb or "".join(sorted(ta)) == "".join(sorted(tb)) or (len(ja) >= 6 and sorted(ja) == sorted(jb)):
        return True
    sh, lg = (ta, tb) if len(ja) <= len(jb) else (tb, ta)
    if len("".join(sh)) >= 5 and "".join(sh) in "".join(lg):
        return True
    sig = [t for t in sh if len(t) >= 3]
    if not sig:
        return False
    return all(any(t == u or (t[0] == u[0] and SequenceMatcher(None, t, u).ratio() >= 0.7) for u in lg) for t in sig)


class Command(BaseCommand):
    help = "Link each project to the payment row of the same customer."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--unlink", action="store_true", help="also take off a wrong link when the customer has no payment row of its own")

    def handle(self, *args, **options):
        dry, unlink_too = options["dry_run"], options["unlink"]
        works = list(ProjectWork.objects.select_related("collection"))
        cols = list(Collection.objects.all())
        moved = checked = linked = 0

        def money(c):
            return "deal %s received %s" % (c.net_value, c.received)

        wrong = [w for w in works if w.collection_id and not same(w.collection.customer, w.name)]
        taken = {w.collection_id for w in works if w.collection_id and w not in wrong}
        for w in wrong:
            c = w.collection
            free = [x for x in cols if x.pk not in taken and x.pk != c.pk and same(x.customer, w.name)]
            if len(free) == 1:
                x = free[0]
                self.stdout.write("   MOVE   %-12s %-28s payment row '%s' (%s)  ->  '%s' (%s, %s)" % (w.project_id or "no id", w.name[:28], c.customer, c.project_id, x.customer, x.project_id, money(x)))
                moved += 1
                taken.add(x.pk)
                w.collection = x
                if not dry:
                    w.save(update_fields=["collection"])
            else:
                checked += 1
                self.stdout.write("   CHECK  %-12s %-28s is linked to the payment row of '%s' (%s, %s): no free row of its own name%s" % (
                    w.project_id or "no id", w.name[:28], c.customer, c.project_id, money(c), "  -> link taken off" if unlink_too else ""))
                if unlink_too:
                    w.collection = None
                    if not dry:
                        w.save(update_fields=["collection"])
                else:
                    taken.add(c.pk)
        taken = {w.collection_id for w in works if w.collection_id}
        for c in cols:
            if c.pk in taken:
                continue
            hits = [w for w in works if not w.collection_id and same(c.customer, w.name)]
            if len(hits) > 1 and c.project_id:                       # the same financial year as the payment row's number
                fy = [w for w in hits if (w.project_id or "")[:7] == c.project_id[:7]]
                hits = fy or hits
            if len(hits) > 1:                                       # then the closest spelling
                best = max(SequenceMatcher(None, "".join(toks(c.customer)), "".join(toks(w.name))).ratio() for w in hits)
                top = [w for w in hits if SequenceMatcher(None, "".join(toks(c.customer)), "".join(toks(w.name))).ratio() >= best - 0.0001]
                if len(top) == 1:
                    hits = top
                else:
                    self.stdout.write("   AMBIGUOUS payment row '%s' (%s): %s" % (c.customer, c.project_id, ", ".join("%s %s" % (w.project_id or "no id", w.name) for w in hits)))
            if len(hits) == 1:
                w = hits[0]
                self.stdout.write("   LINK   %-12s %-28s <- payment row '%s' (%s, %s)" % (w.project_id or "no id", w.name[:28], c.customer, c.project_id, money(c)))
                linked += 1
                w.collection = c
                taken.add(c.pk)
                if not dry:
                    w.save(update_fields=["collection"])
        # the workbook is the main list: the payment row gets the number of its project
        plan = [(w.collection, w.project_id) for w in works if w.collection_id and w.project_id and w.collection.project_id != w.project_id and same(w.collection.customer, w.name)]
        moving = {c.pk for c, _n in plan}
        held = {c.project_id: c for c in cols if c.pk not in moving}
        todo, blocked = [], 0
        for c, new in plan:
            if new in held:
                blocked += 1
                self.stdout.write("   NUMBER %-12s payment row '%s' keeps %s: that number is held by the payment row '%s'" % (new, c.customer, c.project_id, held[new].customer))
            else:
                self.stdout.write("   NUMBER payment row '%-26s' %s  ->  %s" % (c.customer[:26], c.project_id, new))
                todo.append((c, new))
        if todo and not dry:
            with transaction.atomic():
                for c, _n in todo:                       # two steps, so two rows can swap numbers
                    Collection.objects.filter(pk=c.pk).update(project_id="TMP-%d" % c.pk)
                for c, new in todo:
                    Collection.objects.filter(pk=c.pk).update(project_id=new)
        linked_ids = {w.collection_id for w in works if w.collection_id}
        for c in cols:
            if c.pk not in linked_ids:
                self.stdout.write("   NO PROJECT  payment row '%s' (%s, %s): no project of this name is linked to it" % (c.customer, c.project_id, money(c)))
                cand = [w for w in works if same(c.customer, w.name)]
                for w in cand:
                    self.stdout.write("        same name: project %s '%s' (%s)  payment row now: %s" % (w.project_id or "no id", w.name, w.project_stage or "-", w.collection.customer if w.collection_id else "none"))
                if not cand:
                    near = [w for w in works if w.project_id == c.project_id or (c.project_id and w.project_id and w.project_id[-3:] == c.project_id[-3:] and w.project_id[:4] == c.project_id[:4])]
                    for w in near[:3]:
                        self.stdout.write("        same number: project %s '%s'" % (w.project_id, w.name))
        self.stdout.write(self.style.SUCCESS("%d payment rows %s the workbook's number, %d kept theirs." % (len(todo), "would take" if dry else "took", blocked)))
        self.stdout.write(self.style.SUCCESS("%s: %d moved, %d newly linked, %d to check by hand." % ("DRY RUN, nothing saved" if dry else "Done", moved, linked, checked)))
