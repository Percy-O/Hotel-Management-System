from django.urls import path
from . import views
from . import analytics_views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('guest-dashboard/', views.guest_dashboard, name='guest_dashboard'),
    path('profile/', views.profile, name='profile'),
    
    # Analytics
    path('statistics/', analytics_views.HotelStatisticsView.as_view(), name='hotel_statistics'),
    path('statistics/report/', analytics_views.download_statistics_report, name='download_statistics_report'),
    path('statistics/excel/', analytics_views.download_statistics_excel, name='download_statistics_excel'),

    # User Management
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/add/', views.UserCreateView.as_view(), name='user_create'),
    path('users/bulk-delete/', views.bulk_delete_users, name='bulk_delete_users'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='delete_user'),
]