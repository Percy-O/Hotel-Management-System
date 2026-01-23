from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import models
from django.db.models import Count, Q
from .models import Hotel, RoomType, Room, RoomImage, Review
from .forms import RoomTypeForm, RoomForm, BulkRoomForm

# Public Views
class RoomTypeListView(ListView):
    model = RoomType
    template_name = 'hotel/room_type_list.html'
    context_object_name = 'room_types'

    def get_queryset(self):
        # Enforce Tenant Isolation
        if hasattr(self.request, 'tenant') and self.request.tenant:
            queryset = RoomType.objects.filter(tenant=self.request.tenant)
        else:
            return RoomType.objects.none()

        # Handle Filters
        
        # 1. Guests (Capacity)
        guests = self.request.GET.get('guests')
        if guests:
            try:
                guest_count = int(guests)
                queryset = queryset.filter(capacity__gte=guest_count)
            except ValueError:
                pass

        # 2. Category (Name Search)
        category = self.request.GET.get('category')
        if category and category.lower() != 'all':
            # Map 'suites' to 'suite', 'villas' to 'villa' for better matching
            term = category.lower().rstrip('s')
            queryset = queryset.filter(name__icontains=term)

        # 3. Date Availability
        check_in = self.request.GET.get('check_in')
        check_out = self.request.GET.get('check_out')
        
        if check_in and check_out:
            try:
                # Find bookings that overlap with the requested dates
                # Overlap logic: (StartA < EndB) and (EndA > StartB)
                overlapping_bookings = Booking.objects.filter(
                    tenant=self.request.tenant,
                    status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN, Booking.Status.PENDING],
                    check_in_date__lt=check_out,
                    check_out_date__gt=check_in
                )
                
                # Get IDs of rooms that are booked
                booked_room_ids = overlapping_bookings.values_list('room_id', flat=True)
                
                # Find rooms that are NOT booked and belong to this tenant
                available_rooms = Room.objects.filter(
                    tenant=self.request.tenant
                ).exclude(
                    id__in=booked_room_ids
                )
                
                # Get RoomTypes that have at least one available room
                available_room_type_ids = available_rooms.values_list('room_type_id', flat=True).distinct()
                
                queryset = queryset.filter(id__in=available_room_type_ids)
                
            except Exception as e:
                # In case of date parsing errors, ignore filter
                pass

        # Only show room types that have at least one room associated with them
        return queryset.annotate(
            total_rooms=Count('rooms'),
            available_rooms=Count('rooms', filter=Q(rooms__status=Room.Status.AVAILABLE))
        ).filter(total_rooms__gt=0)

class RoomTypeDetailView(DetailView):
    model = RoomType
    template_name = 'hotel/room_type_detail.html'
    context_object_name = 'room_type'

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return RoomType.objects.filter(tenant=self.request.tenant)
        return RoomType.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room_type = self.object
        
        # Calculate available rooms for this type
        # Ensure rooms belong to the same tenant
        total = Room.objects.filter(room_type=room_type, tenant=self.request.tenant).count()
        occupied = Room.objects.filter(
            room_type=room_type, 
            tenant=self.request.tenant,
            status__in=[Room.Status.OCCUPIED, Room.Status.MAINTENANCE, Room.Status.CLEANING]
        ).count()
        context['rooms_available_count'] = total - occupied
        
        # Add reviews
        context['reviews'] = room_type.reviews.all().order_by('-created_at')
        context['average_rating'] = room_type.reviews.aggregate(models.Avg('rating'))['rating__avg']
        
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        guest_name = request.POST.get('guest_name')
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        
        if guest_name and rating and comment:
            Review.objects.create(
                room_type=self.object,
                guest_name=guest_name,
                rating=rating,
                comment=comment
            )
            messages.success(request, "Thank you for your review!")
        
        return redirect('room_detail', pk=self.object.pk)

from django.utils import timezone
from booking.models import Booking

from tenants.utils import has_tenant_permission

# Staff Views
class StaffRoomListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Room
    template_name = 'hotel/staff_room_list.html'
    context_object_name = 'rooms'
    ordering = ['room_number']

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        # Allow ADMIN, MANAGER, RECEPTIONIST, STAFF, CLEANER
        allowed_roles = ['ADMIN', 'MANAGER', 'RECEPTIONIST', 'STAFF', 'CLEANER']
        return has_tenant_permission(self.request.user, tenant, allowed_roles)
    
    def get_queryset(self):
        # Enforce Tenant Isolation
        if hasattr(self.request, 'tenant') and self.request.tenant:
            queryset = Room.objects.select_related('room_type').prefetch_related('bookings').filter(tenant=self.request.tenant)
        else:
            return Room.objects.none()
        
        # If user is a CLEANER, strictly filter to only show CLEANING rooms
        if self.request.user.role == 'CLEANER':
            queryset = queryset.filter(status=Room.Status.CLEANING)
        else:
            # Filter by status if provided in GET params (for other staff)
            status = self.request.GET.get('status')
            if status:
                queryset = queryset.filter(status=status)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Scope counts to tenant
        if hasattr(self.request, 'tenant') and self.request.tenant:
            rooms_qs = Room.objects.filter(tenant=self.request.tenant)
        else:
            rooms_qs = Room.objects.none()
        
        context['total_rooms'] = rooms_qs.count()
        context['available_rooms'] = rooms_qs.filter(status=Room.Status.AVAILABLE).count()
        context['occupied_rooms'] = rooms_qs.filter(status=Room.Status.OCCUPIED).count()
        context['cleaning_rooms'] = rooms_qs.filter(status=Room.Status.CLEANING).count()
        
        # Add current booking info to rooms in context
        # This is a bit manual but allows us to access the specific active booking easily in the template
        now = timezone.now()
        for room in context['rooms']:
            if room.status == Room.Status.OCCUPIED:
                # Find the active booking
                # Priority 1: Explicitly CHECKED_IN (even if time passed, they are still there)
                room.current_booking = room.bookings.filter(
                    status=Booking.Status.CHECKED_IN
                ).first()
                
                # Priority 2: CONFIRMED and within time range (e.g. just checked in physically but status not updated)
                if not room.current_booking:
                    room.current_booking = room.bookings.filter(
                        status=Booking.Status.CONFIRMED,
                        check_in_date__lte=now,
                        check_out_date__gte=now
                    ).first()
        
        return context

class StaffRoomTypeListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = RoomType
    template_name = 'hotel/staff_room_type_list.html'
    context_object_name = 'room_types'

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        allowed_roles = ['ADMIN', 'MANAGER']
        return has_tenant_permission(self.request.user, tenant, allowed_roles)

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return RoomType.objects.filter(tenant=self.request.tenant)
        return RoomType.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add room counts per type
        for rt in context['room_types']:
            rt.total_rooms = rt.rooms.count()
            rt.available_rooms = rt.rooms.filter(status=Room.Status.AVAILABLE).count()
        return context

class RoomStatusUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Room
    fields = ['status']
    template_name = 'hotel/room_status_update.html'
    success_url = reverse_lazy('staff_room_list')

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return Room.objects.filter(tenant=self.request.tenant)
        return Room.objects.none()

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        allowed_roles = ['ADMIN', 'MANAGER', 'RECEPTIONIST', 'STAFF', 'CLEANER']
        return has_tenant_permission(self.request.user, tenant, allowed_roles)

    def form_valid(self, form):
        response = super().form_valid(form)
        room = self.object
        
        # If status changed to AVAILABLE (Cleaned), notify Reception/Manager
        if room.status == Room.Status.AVAILABLE:
             from core.models import Notification
             from django.contrib.auth import get_user_model
             User = get_user_model()
             
             receptionists = User.objects.filter(role__in=[User.Role.RECEPTIONIST, User.Role.MANAGER])
             for recipient in receptionists:
                 Notification.objects.create(
                    recipient=recipient,
                    title="Room Cleaned",
                    message=f"Room {room.room_number} is now clean and available.",
                    notification_type=Notification.Type.SUCCESS,
                    link=reverse_lazy('staff_room_list')
                 )
        
        messages.success(self.request, f"Room {room.room_number} status updated to {room.get_status_display()}.")
        return response

class RoomTypeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = 'hotel/room_type_form.html'
    success_url = reverse_lazy('staff_room_list')

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        allowed_roles = ['ADMIN', 'MANAGER']
        return has_tenant_permission(self.request.user, tenant, allowed_roles)

    def form_valid(self, form):
        # Assign hotel based on current tenant
        tenant = self.request.tenant
        if not tenant:
            messages.error(self.request, "No tenant context found.")
            return redirect('dashboard')
            
        hotel = Hotel.objects.filter(tenant=tenant).first()
        if not hotel:
            # Create a default Hotel object for this tenant if missing
            hotel = Hotel.objects.create(
                tenant=tenant,
                name=tenant.name,
                address="Address not set",
                email=f"info@{tenant.subdomain}.com",
                phone="000-000-0000"
            )
        
        form.instance.hotel = hotel
        form.instance.tenant = tenant # Ensure tenant is also set on RoomType
        response = super().form_valid(form)
        
        # Handle multiple images
        files = self.request.FILES.getlist('gallery_images')
        for f in files:
            RoomImage.objects.create(room_type=self.object, image=f)
            
        return response

class BulkRoomCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = 'hotel/bulk_room_form.html'
    form_class = BulkRoomForm
    success_url = reverse_lazy('staff_room_list')

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        allowed_roles = ['ADMIN', 'MANAGER']
        return has_tenant_permission(self.request.user, tenant, allowed_roles)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = getattr(self.request, 'tenant', None)
        return kwargs

    def form_valid(self, form):
        # Enforce Plan Limits
        tenant = self.request.tenant
        if tenant and tenant.plan:
            current_count = Room.objects.filter(tenant=tenant).count()
            needed = form.cleaned_data.get('number_of_rooms', 0) 
            # BulkRoomForm uses logic inside form_valid, but we need to check before creating loop
            # Actually BulkRoomForm calculates 'needed' based on target.
            # We will check inside the loop or before it.
            
            # Re-calculating needed logic from below to check limit
            room_type = form.cleaned_data['room_type']
            target_count = room_type.number_of_rooms
            current_type_count = Room.objects.filter(room_type=room_type).count()
            needed = max(0, target_count - current_type_count)
            
            if current_count + needed > tenant.plan.max_rooms:
                allowed = tenant.plan.max_rooms - current_count
                messages.error(self.request, f"Plan limit reached. You can only create {allowed} more rooms. Upgrade your plan to add more.")
                return redirect(self.success_url)

        room_type = form.cleaned_data['room_type']
        starting_number = form.cleaned_data['starting_number']
        use_floor_prefix = form.cleaned_data['floor_prefix']
        
        # Calculate how many rooms to create
        # Strategy: Create up to 'number_of_rooms' for this type, skipping existing ones
        current_count = Room.objects.filter(room_type=room_type).count()
        target_count = room_type.number_of_rooms
        
        if current_count >= target_count:
            messages.warning(self.request, f"{room_type.name} already has {current_count} rooms (Target: {target_count}). No new rooms created.")
            return redirect(self.success_url)
            
        needed = target_count - current_count
        created_count = 0
        current_num = starting_number
        
        # Get Tenant Hotel
        hotel = Hotel.objects.filter(tenant=self.request.tenant).first()
        if not hotel:
             # Should ensure hotel exists
             hotel = Hotel.objects.create(tenant=self.request.tenant, name=self.request.tenant.name, address="Default Address", email="info@hotel.com", phone="123")

        while created_count < needed:
            # Double check limit inside loop just in case
            if tenant and tenant.plan and Room.objects.filter(tenant=tenant).count() >= tenant.plan.max_rooms:
                 messages.warning(self.request, f"Stopped at {created_count} rooms due to plan limit.")
                 break

            room_num_str = str(current_num)
            
            # Check if exists
            if not Room.objects.filter(hotel=hotel, room_number=room_num_str).exists():
                floor = ""
                if use_floor_prefix:
                    if len(room_num_str) == 3:
                        floor = room_num_str[0]
                    elif len(room_num_str) >= 4:
                        floor = room_num_str[:2]
                
                Room.objects.create(
                    tenant=self.request.tenant,
                    hotel=hotel,
                    room_type=room_type,
                    room_number=room_num_str,
                    floor=floor,
                    status=Room.Status.AVAILABLE
                )
                created_count += 1
            
            current_num += 1
            
        messages.success(self.request, f"Successfully created {created_count} new rooms for {room_type.name}.")
        return super(FormView, self).form_valid(form)

class RoomCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = 'hotel/room_form.html'
    success_url = reverse_lazy('staff_room_list')

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        return has_tenant_permission(self.request.user, tenant, ['ADMIN', 'MANAGER'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = getattr(self.request, 'tenant', None)
        return kwargs

    def form_valid(self, form):
        # Enforce Plan Limits
        tenant = self.request.tenant
        if tenant and tenant.plan:
             if Room.objects.filter(tenant=tenant).count() >= tenant.plan.max_rooms:
                 messages.error(self.request, "Plan limit reached. Upgrade to add more rooms.")
                 return redirect(self.success_url)

        # Assign default hotel
        hotel = Hotel.objects.filter(tenant=self.request.tenant).first()
        if not hotel:
            # Create a default Hotel object for this tenant if missing
            hotel = Hotel.objects.create(
                tenant=self.request.tenant,
                name=self.request.tenant.name,
                address="Address not set",
                email=f"info@{self.request.tenant.subdomain}.com",
                phone="000-000-0000"
            )
        
        form.instance.hotel = hotel
        form.instance.tenant = self.request.tenant
        return super().form_valid(form)

class RoomTypeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = RoomType
    success_url = reverse_lazy('staff_room_type_list')
    template_name = 'hotel/room_type_confirm_delete.html'

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return RoomType.objects.filter(tenant=self.request.tenant)
        return RoomType.objects.none()

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        return has_tenant_permission(self.request.user, tenant, ['ADMIN', 'MANAGER'])

class RoomDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Room
    success_url = reverse_lazy('staff_room_list')
    template_name = 'hotel/room_confirm_delete.html'

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return Room.objects.filter(tenant=self.request.tenant)
        return Room.objects.none()

    def test_func(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant: return False
        return has_tenant_permission(self.request.user, tenant, ['ADMIN', 'MANAGER'])

@login_required
def bulk_delete_rooms(request):
    if not request.user.is_staff and request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('staff_room_list')
        
    if request.method == 'POST':
        room_ids = request.POST.getlist('selected_rooms')
        if room_ids:
            # Enforce Tenant Isolation
            if hasattr(request, 'tenant') and request.tenant:
                deleted_count, _ = Room.objects.filter(id__in=room_ids, tenant=request.tenant).delete()
                messages.success(request, f"Successfully deleted {deleted_count} rooms.")
            else:
                messages.error(request, "Tenant context missing.")
        else:
            messages.warning(request, "No rooms selected for deletion.")
            
    return redirect('staff_room_list')