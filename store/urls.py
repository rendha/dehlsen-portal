from django.contrib.auth import views as auth_views
from django.urls import path

from . import pwa, views

urlpatterns = [
    path("", views.home, name="store_home"),
    path("import/", views.import_quotation, name="import"),
    path("customer/<int:pk>/", views.customer_detail, name="customer"),
    path("customer/<int:pk>/export/<str:source>/", views.export_csv, name="export"),
    path("stock/", views.stock_list, name="stock"),
    path("boss/", views.boss_home, name="boss"),
    path("boss/customer/<int:pk>/", views.boss_customer, name="boss_customer"),
    path("boss/<str:kind>/", views.boss_detail, name="boss_detail"),
    path("accounts/", views.accounts_home, name="accounts"),
    path("accounts/<int:pk>/", views.accounts_customer, name="accounts_customer"),
]
