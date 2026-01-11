"""
URL configuration for hms_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),
    
    # Auth & Dashboard Shortcuts
    path("login/", account_views.login_view, name="login"),
    path("register/", account_views.register_view, name="register"),
    path("logout/", account_views.logout_view, name="logout"),
    path("dashboard/", account_views.dashboard, name="dashboard"),

    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("hotel/", include("hotel.urls")),
    path("booking/", include("booking.urls")),
    path("billing/", include("billing.urls")),
    path("guests/", include("guests.urls")),
    path("services/", include("services.urls")),
    path("events/", include("events.urls")),
    path("gym/", include("gym.urls")),
    path("tenants/", include("tenants.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Add shortcuts at the end to override names if needed, or just ensure they are available
urlpatterns += [
    path("login/", account_views.login_view, name="login"),
    path("register/", account_views.register_view, name="register"),
    path("logout/", account_views.logout_view, name="logout"),
    path("dashboard/", account_views.dashboard, name="dashboard"),
]

