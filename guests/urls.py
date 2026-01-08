from django.urls import path
from . import views

urlpatterns = [
    path('list/', views.guest_list, name='guest_list'),
    path('detail/', views.guest_detail, name='guest_detail'),
    path('toggle-vip/<int:profile_id>/', views.toggle_vip, name='toggle_vip'),
]
