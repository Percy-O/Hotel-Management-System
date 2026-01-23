from django.urls import path
from . import views

urlpatterns = [
    path('book/<int:room_type_id>/', views.create_booking, name='create_booking'),
    path('booking/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('manage/', views.booking_list, name='booking_list'),
    path('add/', views.add_booking_selection, name='add_booking_selection'),
    path('verify/', views.verify_booking, name='verify_booking'),
    path('booking/<int:pk>/check-in/', views.check_in_booking, name='check_in_booking'),
    path('booking/<int:pk>/check-out/', views.check_out_booking, name='check_out_booking'),
    path('booking/<int:pk>/receipt/', views.download_receipt, name='download_receipt'),
    path('booking/<int:pk>/barcode/', views.download_barcode, name='download_barcode'),
    path('booking/<int:pk>/pass/', views.view_barcode_pass, name='view_barcode_pass'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('booking/<int:pk>/extend/', views.extend_booking, name='extend_booking'),
]
