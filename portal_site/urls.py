from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sales/", include("quotations.urls")),       # Sales    -> the quotation app
    path("project/", include("store.urls")),          # Project  -> the materials app
    path("service/", include("cleaning.urls")),       # Service  -> the cleaning manager
    path("", include("portal.urls")),                 # login, home (the four buttons), Task, install-as-app files
]
