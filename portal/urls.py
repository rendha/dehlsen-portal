from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import path

from . import project_work, views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", login_not_required(auth_views.LoginView.as_view(
        template_name="portal/login.html", redirect_authenticated_user=True)), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("targets/", views.targets, name="targets"),
    path("collections/", views.collections, name="collections"),
    path("collections/<int:pk>/pay/", views.collection_pay, name="collection_pay"),
    path("collections/payment/<int:pk>/delete/", views.collection_pay_delete, name="collection_pay_delete"),
    path("leads/", views.leads, name="leads"),
    path("leads/add/", views.lead_new, name="lead_new"),
    path("leads/<int:pk>/site/", views.lead_site, name="lead_site"),
    path("leads/<int:pk>/photo/<int:photo_id>/", views.lead_photo, name="lead_photo"),
    path("leads/<int:pk>/quick/", views.lead_quick, name="lead_quick"),
    path("leads/<int:pk>/update/", views.lead_update, name="lead_update"),
    path("leads/<int:pk>/type/", views.lead_type, name="lead_type"),
    path("leads/<int:pk>/won/", views.lead_won, name="lead_won"),
    path("leads/<int:pk>/lost/", views.lead_lost, name="lead_lost"),
    path("leads/<int:pk>/done/", views.lead_done, name="lead_done"),
    path("progress/", project_work.progress, name="progress"),
    path("progress/<int:pk>/update/", project_work.progress_update, name="progress_update"),
    path("progress/<int:pk>/", project_work.project_detail, name="progress_detail"),
    path("task/", views.task, name="task"),
    path("task/events/", views.task_events, name="task_events"),
    path("task/new/", views.task_new, name="task_new"),
    path("task/mine/", views.task_mine, name="task_mine"),
    path("task/<int:pk>/", views.task_detail, name="task_detail"),
    path("task/<int:pk>/done/", views.task_done, name="task_done"),
    path("task/push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("task/push/test/", views.push_test, name="push_test"),
    # the files that make the site installable as an app on a phone (one for the whole site)
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
]
