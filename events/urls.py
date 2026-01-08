from django.urls import path
from . import views

urlpatterns = [
    # Hall Management
    path('halls/', views.EventHallListView.as_view(), name='event_hall_list'),
    path('halls/create/', views.EventHallCreateView.as_view(), name='event_hall_create'),
    path('halls/<int:pk>/', views.EventHallDetailView.as_view(), name='event_hall_detail'),
    path('halls/<int:pk>/edit/', views.EventHallUpdateView.as_view(), name='event_hall_update'),
    path('halls/<int:pk>/delete/', views.EventHallDeleteView.as_view(), name='event_hall_delete'),

    # Booking Management
    path('bookings/', views.EventBookingListView.as_view(), name='event_booking_list'),
    path('bookings/create/', views.EventBookingCreateView.as_view(), name='event_booking_create'),
    path('bookings/<int:pk>/', views.EventBookingDetailView.as_view(), name='event_booking_detail'),
    path('bookings/<int:pk>/status/<str:status>/', views.update_booking_status, name='update_booking_status'),
]
