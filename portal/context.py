def portal(request):
    """The red number on the Task button: tasks waiting for this person."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"task_badge": 0}
    try:
        from .models import Task
        return {"task_badge": Task.objects.filter(assigned_to=user, done=False).count()}
    except Exception:                       # e.g. the tables do not exist yet (before migrate): never break a page for a badge
        return {"task_badge": 0}
