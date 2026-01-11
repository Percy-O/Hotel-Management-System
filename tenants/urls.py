from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_tenant, name='create_tenant'),
]
