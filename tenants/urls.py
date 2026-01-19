from django.urls import path
from . import views
from . import platform_views

urlpatterns = [
    # Tenant Routes (Client Side)
    path('create/', views.create_tenant, name='create_tenant'),
    path('payment/<int:tenant_id>/', views.tenant_payment, name='tenant_payment'),
    path('payment/<int:tenant_id>/process/', views.process_payment, name='process_payment'),
    path('upgrade/<int:plan_id>/', views.upgrade_subscription, name='upgrade_subscription'),
    path('settings/', views.TenantSettingsView.as_view(), name='tenant_settings'),
    path('settings/cancel-subscription/', views.cancel_subscription, name='cancel_subscription'),
    path('settings/enable-auto-renew/', views.enable_auto_renew, name='enable_auto_renew'),
    
    # Platform Admin Routes (Super Admin)
    path('platform/', platform_views.platform_dashboard, name='platform_dashboard'),
    
    # Tenants
    path('platform/tenants/', platform_views.TenantListView.as_view(), name='platform_tenants'),
    path('platform/tenants/<int:pk>/edit/', platform_views.TenantUpdateView.as_view(), name='platform_tenant_edit'),
    path('platform/tenants/<int:pk>/delete/', platform_views.TenantDeleteView.as_view(), name='platform_tenant_delete'),
    
    # Users
    path('platform/users/', platform_views.PlatformUserListView.as_view(), name='platform_users'),
    path('platform/users/<int:pk>/edit/', platform_views.PlatformUserUpdateView.as_view(), name='platform_user_edit'),
    path('platform/users/<int:pk>/delete/', platform_views.PlatformUserDeleteView.as_view(), name='platform_user_delete'),
    
    # Subscriptions / Plans
    path('platform/plans/', platform_views.PlanListView.as_view(), name='platform_subscriptions'),
    path('platform/plans/add/', platform_views.PlanCreateView.as_view(), name='platform_plan_add'),
    path('platform/plans/<int:pk>/', platform_views.PlanDetailView.as_view(), name='platform_plan_detail'),
    path('platform/plans/<int:pk>/edit/', platform_views.PlanUpdateView.as_view(), name='platform_plan_edit'),
    
    # Finance / Payments
    path('platform/finance/transactions/', platform_views.PlatformPaymentListView.as_view(), name='platform_payments'),
    path('platform/finance/settings/', platform_views.PlatformFinanceSettingsView.as_view(), name='platform_finance_settings'),
    path('platform/settings/payments/<str:provider>/', platform_views.PlatformGatewayUpdateView.as_view(), name='platform_gateway_edit'),

    # System
    path('platform/settings/', platform_views.PlatformSettingsView.as_view(), name='platform_settings'),
    path('platform/logs/', platform_views.PlatformLogListView.as_view(), name='platform_logs'),
]
