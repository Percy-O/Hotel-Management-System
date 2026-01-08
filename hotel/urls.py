from django.urls import path
from . import views

urlpatterns = [
    # Public URLs
    path('rooms/', views.RoomTypeListView.as_view(), name='room_list'),
    path('rooms/<int:pk>/', views.RoomTypeDetailView.as_view(), name='room_detail'),
    
    # Staff URLs
    path('staff/rooms/', views.StaffRoomListView.as_view(), name='staff_room_list'),
    path('staff/room-types/', views.StaffRoomTypeListView.as_view(), name='staff_room_type_list'),
    path('staff/rooms/add/', views.RoomCreateView.as_view(), name='room_create'),
    path('staff/rooms/bulk-add/', views.BulkRoomCreateView.as_view(), name='bulk_room_create'),
    path('staff/rooms/bulk-delete/', views.bulk_delete_rooms, name='bulk_delete_rooms'),
    path('staff/rooms/<int:pk>/delete/', views.RoomDeleteView.as_view(), name='room_delete'),
    path('staff/room-types/add/', views.RoomTypeCreateView.as_view(), name='room_type_create'),
    path('staff/room-types/<int:pk>/delete/', views.RoomTypeDeleteView.as_view(), name='room_type_delete'),
    path('staff/rooms/<int:pk>/status/', views.RoomStatusUpdateView.as_view(), name='room_status_update'),
]
