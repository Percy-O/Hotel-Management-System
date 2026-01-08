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
        # Only show room types that have at least one room associated with them
        return RoomType.objects.annotate(
            total_rooms=Count('rooms'),
            available_rooms=Count('rooms', filter=Q(rooms__status=Room.Status.AVAILABLE))
        ).filter(total_rooms__gt=0)

class RoomTypeDetailView(DetailView):
    model = RoomType
    template_name = 'hotel/room_type_detail.html'
    context_object_name = 'room_type'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room_type = self.object
        
        # Calculate available rooms for this type
        total = Room.objects.filter(room_type=room_type).count()
        occupied = Room.objects.filter(
            room_type=room_type, 
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

# Staff Views
class StaffRoomListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Room
    template_name = 'hotel/staff_room_list.html'
    context_object_name = 'rooms'
    ordering = ['room_number']

    def test_func(self):
        return self.request.user.is_staff or self.request.user.role in ['ADMIN', 'MANAGER', 'RECEPTIONIST', 'STAFF', 'CLEANER']
    
    def get_queryset(self):
        queryset = Room.objects.select_related('room_type').prefetch_related('bookings').all()
        
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
        context['total_rooms'] = Room.objects.count()
        context['available_rooms'] = Room.objects.filter(status=Room.Status.AVAILABLE).count()
        context['occupied_rooms'] = Room.objects.filter(status=Room.Status.OCCUPIED).count()
        context['cleaning_rooms'] = Room.objects.filter(status=Room.Status.CLEANING).count()
        
        # Add current booking info to rooms in context
        # This is a bit manual but allows us to access the specific active booking easily in the template
        now = timezone.now()
        for room in context['rooms']:
            if room.status == Room.Status.OCCUPIED:
                # Find the active booking
                room.current_booking = room.bookings.filter(
                    status__in=[Booking.Status.CHECKED_IN, Booking.Status.CONFIRMED],
                    check_in_date__lte=now,
                    check_out_date__gte=now
                ).first()
        
        return context

class StaffRoomTypeListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = RoomType
    template_name = 'hotel/staff_room_type_list.html'
    context_object_name = 'room_types'

    def test_func(self):
        return self.request.user.is_staff

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

    def test_func(self):
        return self.request.user.is_staff or self.request.user.role in ['ADMIN', 'MANAGER', 'RECEPTIONIST', 'STAFF', 'CLEANER']

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
        return self.request.user.is_staff

    def form_valid(self, form):
        # Assign default hotel (assuming single hotel system for now, or pick first)
        # If Hotel is required, we should set it. Assuming ID 1 exists or user selects it.
        # But RoomTypeForm might handle it or we set it here.
        # Let's assume we use the first hotel or create one if none.
        hotel = Hotel.objects.first()
        if not hotel:
            hotel = Hotel.objects.create(name="Grand Hotel", address="Default Address", email="info@grandhotel.com", phone="1234567890")
        
        form.instance.hotel = hotel
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
        return self.request.user.is_staff

    def form_valid(self, form):
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
        
        hotel = Hotel.objects.first() # Assume single hotel
        
        while created_count < needed:
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
                    hotel=hotel,
                    room_type=room_type,
                    room_number=room_num_str,
                    floor=floor,
                    status=Room.Status.AVAILABLE
                )
                created_count += 1
            
            current_num += 1
            
        messages.success(self.request, f"Successfully created {created_count} new rooms for {room_type.name}.")
        return super().form_valid(form)

class RoomCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = 'hotel/room_form.html'
    success_url = reverse_lazy('staff_room_list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        # Assign default hotel
        hotel = Hotel.objects.first()
        if not hotel:
            hotel = Hotel.objects.create(name="Grand Hotel", address="Default Address", email="info@grandhotel.com", phone="1234567890")
        
        form.instance.hotel = hotel
        return super().form_valid(form)

class RoomTypeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = RoomType
    success_url = reverse_lazy('staff_room_type_list')
    template_name = 'hotel/room_type_confirm_delete.html'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.role == 'ADMIN'

class RoomDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Room
    success_url = reverse_lazy('staff_room_list')
    template_name = 'hotel/room_confirm_delete.html'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.role == 'ADMIN'

@login_required
def bulk_delete_rooms(request):
    if not request.user.is_staff and request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('staff_room_list')
        
    if request.method == 'POST':
        room_ids = request.POST.getlist('selected_rooms')
        if room_ids:
            deleted_count, _ = Room.objects.filter(id__in=room_ids).delete()
            messages.success(request, f"Successfully deleted {deleted_count} rooms.")
        else:
            messages.warning(request, "No rooms selected for deletion.")
            
    return redirect('staff_room_list')