from django.urls import path
from . import views

urlpatterns = [
    path('menu/', views.menu_list, name='menu_list'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('place-order/', views.place_order, name='place_order'),
    path('staff/orders/', views.staff_order_list, name='staff_order_list'),
    path('staff/orders/history/', views.staff_order_history, name='staff_order_history'),
    path('staff/orders/<int:order_id>/update/', views.update_order_status, name='update_order_status'),

    # Housekeeping
    path('housekeeping/request/', views.request_housekeeping, name='request_housekeeping'),
    path('housekeeping/my-requests/', views.my_requests, name='my_requests'),
    path('staff/housekeeping/', views.staff_housekeeping_list, name='staff_housekeeping_list'),
    path('staff/housekeeping/<int:pk>/update/', views.update_housekeeping_status, name='update_housekeeping_status'),
    
    # Housekeeping Management
    path('manage/housekeeping/', views.HousekeepingServiceTypeListView.as_view(), name='housekeeping_service_type_list'),
    path('manage/housekeeping/add/', views.HousekeepingServiceTypeCreateView.as_view(), name='housekeeping_service_type_create'),
    path('manage/housekeeping/settings/', views.HousekeepingSettingsView.as_view(), name='housekeeping_settings'),
    path('manage/housekeeping/<int:pk>/edit/', views.HousekeepingServiceTypeUpdateView.as_view(), name='housekeeping_service_type_update'),
    path('manage/housekeeping/<int:pk>/delete/', views.HousekeepingServiceTypeDeleteView.as_view(), name='housekeeping_service_type_delete'),

    # Menu Management
    path('manage/menu/', views.MenuItemListView.as_view(), name='menu_item_list'),
    path('manage/menu/add/', views.MenuItemCreateView.as_view(), name='menu_item_create'),
    path('manage/menu/<int:pk>/edit/', views.MenuItemUpdateView.as_view(), name='menu_item_update'),
    path('manage/menu/<int:pk>/delete/', views.MenuItemDeleteView.as_view(), name='menu_item_delete'),
]
