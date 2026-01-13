from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('update-theme/', views.update_theme, name='update_theme'),
    path('settings/', views.settings_view, name='settings'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/test/', views.test_notification, name='test_notification'),
    path('settings/test-email/', views.test_email_config, name='test_email_config'),
    path('api/notifications/unread/', views.get_unread_notifications, name='get_unread_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
]
