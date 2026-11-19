def portal(request):
    """The red numbers on the Task and Meetings buttons: tasks and meeting action items waiting for this person."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"task_badge": 0, "meeting_badge": 0, "finance_access": False}
    out = {"task_badge": 0, "meeting_badge": 0, "finance_access": False}
    try:
        from .models import Task
        out["task_badge"] = Task.objects.filter(assigned_to=user, done=False).count()
    except Exception:                       # e.g. the tables do not exist yet (before migrate): never break a page for a badge
        pass
    try:
        from .meetings import open_actions_of
        out["meeting_badge"] = open_actions_of(user).count()      # meeting action items waiting for this person
    except Exception:
        pass
    try:
        from finance.views import can_view
        out["finance_access"] = can_view(user)      # who sees the Accounts button
    except Exception:
        pass
    return out
