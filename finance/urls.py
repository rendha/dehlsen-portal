from django.urls import path

from . import receivables, views

urlpatterns = [
    path("", views.payables, name="fin_home"),
    path("proformas/", views.proformas, name="fin_proformas"),
    path("proformas/new/", views.proforma_new, name="fin_proforma_new"),
    path("proformas/<int:pk>/", views.proforma_detail, name="fin_proforma"),
    path("proformas/<int:pk>/edit/", views.proforma_edit, name="fin_proforma_edit"),
    path("proformas/<int:pk>/status/", views.proforma_status, name="fin_proforma_status"),
    path("advances/", views.advances, name="fin_advances"),
    path("invoices/new/", views.invoice_new, name="fin_invoice_new"),
    path("invoices/<int:pk>/", views.invoice_detail, name="fin_invoice"),
    path("invoices/<int:pk>/edit/", views.invoice_edit, name="fin_invoice_edit"),
    path("invoices/<int:pk>/flag/", views.invoice_flag, name="fin_invoice_flag"),
    path("pay/<str:kind>/<int:pk>/", views.payment_add, name="fin_pay"),
    path("payment/<int:pk>/delete/", views.payment_delete, name="fin_pay_delete"),
    path("vendors/", views.vendors, name="fin_vendors"),
    path("vendors/new/", views.vendor_edit, name="fin_vendor_new"),
    path("vendors/<int:pk>/", views.vendor_edit, name="fin_vendor"),
    path("confirm/", views.to_confirm, name="fin_confirm"),
    path("confirm/<str:kind>/<int:pk>/clear/", views.confirm_clear, name="fin_confirm_clear"),
    path("file/<int:pk>/", views.attachment_file, name="fin_file"),
    path("export/", views.export_payables, name="fin_export"),
    path("receivables/", receivables.receivables, name="fin_receivables"),
    path("receivables/<int:pk>/", receivables.receivable, name="fin_receivable"),
    path("received/", receivables.received, name="fin_received"),
    path("received/<int:pk>/tick/", receivables.received_tick, name="fin_received_tick"),
    path("receipt/<int:pk>/confirm/", receivables.receipt_confirm, name="fin_receipt_confirm"),
    path("receipt/<int:pk>/reject/", receivables.receipt_reject, name="fin_receipt_reject"),
]
