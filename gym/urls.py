from django.urls import path
from . import views

urlpatterns = [
    # Plan Management
    path('plans/', views.GymPlanListView.as_view(), name='gym_plan_list'),
    path('plans/create/', views.GymPlanCreateView.as_view(), name='gym_plan_create'),
    path('plans/<int:pk>/edit/', views.GymPlanUpdateView.as_view(), name='gym_plan_update'),
    path('plans/<int:pk>/delete/', views.GymPlanDeleteView.as_view(), name='gym_plan_delete'),

    # Membership Management
    path('memberships/', views.GymMembershipListView.as_view(), name='gym_membership_list'),
    path('memberships/join/', views.GymMembershipCreateView.as_view(), name='gym_membership_create'),
    path('memberships/<int:pk>/', views.GymMembershipDetailView.as_view(), name='gym_membership_detail'),
    path('memberships/<int:pk>/cancel/', views.cancel_membership, name='cancel_membership'),
]
