from django.urls import path
from . import views

urlpatterns = [
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('my-invoices/', views.my_invoices, name='my_invoices'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/pay/', views.make_payment, name='make_payment'),
    path('payment/select/<int:invoice_id>/', views.payment_selection, name='payment_selection'),
    path('payment/verify/<str:gateway>/', views.verify_payment, name='verify_payment'),
    path('payment/settings/', views.payment_settings, name='payment_settings'),
]
