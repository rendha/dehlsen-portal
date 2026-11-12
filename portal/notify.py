"""Telling a person about a task: the WhatsApp link and the phone alert (push)."""
import json
import os
import re
import urllib.parse

from .models import PushSubscription


def name_of(user):
    return (user.get_full_name() or user.get_username()) if user else "Someone"


def whatsapp_number(user):
    """Digits with country code for wa.me, or '' when the person has no number.  A 10-digit number is taken as Indian."""
    profile = getattr(user, "portal_profile", None) if user else None
    digits = re.sub(r"\D", "", profile.whatsapp if profile else "")
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def message_text(task, link):
    lines = ["Hi %s, new task from %s:" % (name_of(task.assigned_to).split(" ")[0], name_of(task.created_by)), task.task_type.name]
    if task.details:
        lines.append(task.details)
    lines.append("Due: %s (%s)" % (task.due_text(), task.left_text()))
    lines.append("Open: " + link)
    return "\n".join(lines)


def whatsapp_link(task, link):
    number = whatsapp_number(task.assigned_to)
    text = urllib.parse.quote(message_text(task, link))
    return ("https://wa.me/%s?text=%s" % (number, text)) if number else ""


def push_enabled():
    return bool(os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY"))


def send_push(user, title, body, url="/task/mine/"):
    """Phone alert to every phone of this person.  Silent when alerts are not switched on or the library is missing."""
    if not push_enabled() or user is None:
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return 0
    sent = 0
    payload = json.dumps({"title": title, "body": body, "url": url})
    claims = {"sub": os.environ.get("VAPID_EMAIL", "mailto:admin@example.com")}
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=payload, vapid_private_key=os.environ["VAPID_PRIVATE_KEY"], vapid_claims=dict(claims), timeout=8)
            sent += 1
        except WebPushException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status in (404, 410):          # the phone removed the permission: forget it
                sub.delete()
        except Exception:
            pass
    return sent
