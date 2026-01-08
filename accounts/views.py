from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db.models import Sum, Count
from .forms import RegistrationForm, LoginForm, UserForm
from .models import User
from booking.models import Booking
from billing.models import Invoice
from hotel.models import Room
from services.models import GuestOrder
from events.models import EventBooking
from gym.models import GymMembership
from django.utils import timezone

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})

from django.urls import reverse

def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # Check purpose of visit to redirect accordingly
            visit_purpose = request.POST.get('visit_purpose', 'hotel')
            dashboard_url = reverse('dashboard')
            
            if visit_purpose == 'event':
                return redirect(f'{dashboard_url}?welcome=event')
            elif visit_purpose == 'gym':
                return redirect(f'{dashboard_url}?welcome=gym')
                
            return redirect('dashboard')
        else:
            print("Registration Form Errors:", form.errors) # Debugging
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def dashboard(request):
    user = request.user
    
    # Check for specific roles first before default guest fallback
    
    # Cleaner Dashboard
    if user.role == User.Role.CLEANER:
        # Get rooms assigned or just all cleaning rooms
        cleaning_rooms = Room.objects.filter(status=Room.Status.CLEANING)
        return render(request, 'accounts/dashboard_cleaner.html', {'cleaning_rooms': cleaning_rooms})

    # Kitchen Staff Dashboard
    if user.role == User.Role.KITCHEN:
        return redirect('staff_order_list')

    # Receptionist Dashboard
    if user.role == User.Role.RECEPTIONIST:
        # Focus on Today's Check-ins/outs
        from django.utils import timezone
        today = timezone.now().date()
        
        check_ins = Booking.objects.filter(check_in_date__date=today, status=Booking.Status.CONFIRMED)
        check_outs = Booking.objects.filter(check_out_date__date=today, status=Booking.Status.CHECKED_IN)
        available_rooms_count = Room.objects.filter(status=Room.Status.AVAILABLE).count()
        
        context = {
            'check_ins': check_ins,
            'check_outs': check_outs,
            'available_rooms_count': available_rooms_count,
        }
        return render(request, 'accounts/dashboard_receptionist.html', context)

    # If not staff/superuser and not one of the special roles above, send to guest dashboard
    if not user.is_staff and not user.is_superuser:
        guest_dashboard_url = reverse('guest_dashboard')
        welcome_param = request.GET.get('welcome')
        if welcome_param:
            return redirect(f"{guest_dashboard_url}?welcome={welcome_param}")
        return redirect('guest_dashboard')

    # Admin & Manager Dashboard (Full Stats)
    # Gather Statistics
    total_guests = Booking.objects.values('guest_email').distinct().count()
    
    total_revenue = Invoice.objects.filter(
        status=Invoice.Status.PAID
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_bookings = Booking.objects.count()
    
    # Room Status
    total_rooms = Room.objects.count()
    occupied_rooms = Room.objects.filter(status=Room.Status.OCCUPIED).count()
    available_rooms = Room.objects.filter(status=Room.Status.AVAILABLE).count()
    
    # Recent Bookings
    recent_bookings = Booking.objects.select_related('room', 'room__room_type').order_by('-created_at')[:5]

    context = {
        'total_guests': total_guests,
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': available_rooms,
        'recent_bookings': recent_bookings,
    }
    
    return render(request, 'accounts/dashboard.html', context)

@login_required
def guest_dashboard(request):
    if request.user.is_staff:
        return redirect('dashboard')
        
    # Set visit purpose in session if provided, otherwise get from session
    welcome_param = request.GET.get('welcome')
    if welcome_param in ['event', 'gym', 'hotel']:
        request.session['visit_purpose'] = welcome_param
    else:
        welcome_param = request.session.get('visit_purpose')
    
    # Auto-detect guest type if not set
    if not welcome_param:
        has_active_gym = GymMembership.objects.filter(user=request.user, status='ACTIVE').exists()
        has_event = EventBooking.objects.filter(user=request.user, status__in=['CONFIRMED', 'PENDING']).exists()
        has_hotel = Booking.objects.filter(user=request.user, status__in=['CONFIRMED', 'CHECKED_IN', 'PENDING']).exists()
        
        if has_active_gym and not has_hotel and not has_event:
             welcome_param = 'gym'
        elif has_event and not has_hotel:
             welcome_param = 'event'
        else:
             welcome_param = 'hotel' # Default
             
        request.session['visit_purpose'] = welcome_param
    
    # Guest Stats
    bookings = Booking.objects.filter(user=request.user)
    total_bookings = bookings.count()
    active_bookings = bookings.filter(status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN, Booking.Status.PENDING]).count()
    
    # Calculate Total Spent (Bookings + Room Service Orders)
    booking_spent = bookings.aggregate(total=Sum('total_price'))['total'] or 0
    
    # Sum of all non-cancelled orders
    order_spent = GuestOrder.objects.filter(
        user=request.user
    ).exclude(
        status='CANCELLED'
    ).aggregate(total=Sum('total_price'))['total'] or 0
    
    total_spent = booking_spent + order_spent
    
    recent_bookings = bookings.order_by('-created_at')[:3]
    
    # Event Bookings
    event_bookings = EventBooking.objects.filter(user=request.user).order_by('-created_at')
    
    # Gym Memberships
    gym_memberships = GymMembership.objects.filter(user=request.user).order_by('-end_date')
    
    context = {
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'total_spent': total_spent,
        'recent_bookings': recent_bookings,
        'event_bookings': event_bookings,
        'gym_memberships': gym_memberships,
        'welcome_mode': welcome_param,
    }
    return render(request, 'accounts/guest_dashboard.html', context)

@login_required
def profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.phone_number = request.POST.get('phone_number')
        
        # Handle Password Change if provided
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)
            login(request, user) # Re-login after password change
            
        user.save()
        return redirect('profile')
        
    return render(request, 'accounts/profile.html')

# User Management Views
class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    
    def test_func(self):
        return self.request.user.is_staff and self.request.user.role in ['ADMIN', 'MANAGER']

class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_list')
    
    def test_func(self):
        return self.request.user.is_staff and self.request.user.role in ['ADMIN', 'MANAGER']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

class UserDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('user_list')
    
    def test_func(self):
        # Prevent self-deletion
        if self.get_object() == self.request.user:
            return False
        return self.request.user.is_staff and self.request.user.role in ['ADMIN', 'MANAGER']

@login_required
def bulk_delete_users(request):
    if not request.user.is_staff or request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "Access denied.")
        return redirect('user_list')
        
    if request.method == 'POST':
        user_ids = request.POST.getlist('selected_users')
        if user_ids:
            # Prevent deleting self
            user_ids = [uid for uid in user_ids if int(uid) != request.user.id]
            
            deleted_count, _ = User.objects.filter(id__in=user_ids).delete()
            messages.success(request, f"Successfully deleted {deleted_count} users.")
        else:
            messages.warning(request, "No users selected for deletion.")
            
    return redirect('user_list')

class UserUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_list')
    
    def test_func(self):
        return self.request.user.is_staff and self.request.user.role in ['ADMIN', 'MANAGER']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
