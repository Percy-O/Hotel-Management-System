from django.contrib import admin
from .models import Tenant, Domain, Membership, Plan

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'max_rooms', 'is_public')
    list_filter = ('is_public', 'currency')
    search_fields = ('name',)

class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'subdomain', 'owner', 'created_at', 'is_active')
    search_fields = ('name', 'slug', 'owner__email')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [DomainInline, MembershipInline]

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'date_joined', 'is_active')
    list_filter = ('tenant', 'role', 'is_active')
    search_fields = ('user__email', 'tenant__name')
