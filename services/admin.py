from django.contrib import admin
from .models import MenuItem, GuestOrder, OrderItem, HousekeepingRequest, HousekeepingServiceType

@admin.register(HousekeepingServiceType)
class HousekeepingServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'is_active')
    search_fields = ('name',)

@admin.register(HousekeepingRequest)
class HousekeepingRequestAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'service_type', 'request_type', 'status', 'created_at')
    list_filter = ('status', 'service_type', 'created_at')
    search_fields = ('room_number', 'user__username')

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name', 'description')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(GuestOrder)
class GuestOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'room_number', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'room_number')
    inlines = [OrderItemInline]
    readonly_fields = ('total_price', 'created_at')
