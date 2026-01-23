from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about_us, name='about_us'),
    path('contact/', views.contact_us, name='contact_us'),
    path('faqs/', views.faqs_view, name='faqs'),
    path('privacy/', views.privacy_policy_view, name='privacy_policy'),
    path('terms/', views.terms_conditions_view, name='terms_conditions'),
    path('update-theme/', views.update_theme, name='update_theme'),
    path('settings/', views.settings_view, name='settings'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/test/', views.test_notification, name='test_notification'),
    path('settings/test-email/', views.test_email_config, name='test_email_config'),
    path('api/notifications/unread/', views.get_unread_notifications, name='get_unread_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('dashboard/messages/', views.contact_message_list, name='contact_message_list'),
    path('dashboard/messages/<int:message_id>/', views.contact_message_detail, name='contact_message_detail'),
    
    # Facilities Management
    path('dashboard/facilities/', views.HotelFacilityListView.as_view(), name='facility_list'),
    path('dashboard/facilities/create/', views.HotelFacilityCreateView.as_view(), name='facility_create'),
    path('dashboard/facilities/<int:pk>/edit/', views.HotelFacilityUpdateView.as_view(), name='facility_update'),
    path('dashboard/facilities/<int:pk>/delete/', views.HotelFacilityDeleteView.as_view(), name='facility_delete'),
]
