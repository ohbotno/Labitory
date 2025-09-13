# booking/views/viewsets/bookings.py
"""
Booking-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime, timedelta

from ...models import Booking, WaitingListEntry, BookingHistory, UserProfile
from ...serializers import BookingSerializer, WaitingListEntrySerializer
from ..modules.api import IsOwnerOrManagerPermission, CanViewResourceCalendar
from ...utils.security_utils import APIRateLimitMixin
from ...utils.query_optimization import OptimizedQuerySets, PaginationMixin


class BookingViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for bookings with full CRUD operations and rate limiting."""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrManagerPermission]
    
    def get_permissions(self):
        """Override permissions for specific actions."""
        if self.action == 'calendar':
            # For calendar action, use CanViewResourceCalendar permission
            # which checks if user can view the specific resource's calendar
            permission_classes = [permissions.IsAuthenticated, CanViewResourceCalendar]
        else:
            # For all other actions, use default permissions
            permission_classes = self.permission_classes
        
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter bookings based on user role and query parameters."""
        user = self.request.user
        # Use optimized queryset with all necessary prefetches
        queryset = OptimizedQuerySets.get_booking_queryset(
            include_attendees=True,
            include_history=False,
            include_checkin_events=True
        )
        
        try:
            user_profile = user.userprofile
            
            # Filter by user role
            if user_profile.role in ['technician', 'sysadmin']:
                # Managers can see all bookings
                pass
            elif user_profile.role == 'lecturer':
                # Lecturers can see their bookings and their group's bookings
                queryset = queryset.filter(
                    Q(user=user) | 
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True)
                )
            else:
                # Students/researchers see their own bookings and shared group bookings
                queryset = queryset.filter(
                    Q(user=user) |
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True) |
                    Q(attendees=user)
                ).distinct()
        
        except UserProfile.DoesNotExist:
            queryset = queryset.filter(user=user)
        
        # Filter by query parameters
        resource_id = self.request.query_params.get('resource')
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            try:
                # Parse date strings and make them timezone-aware
                start_datetime = timezone.make_aware(
                    datetime.strptime(start_date, '%Y-%m-%d')
                )
                end_datetime = timezone.make_aware(
                    datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                )
                queryset = queryset.filter(
                    start_time__gte=start_datetime,
                    end_time__lte=end_datetime
                )
            except ValueError:
                # If date parsing fails, skip filtering
                pass
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('start_time')
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be approved"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'approved'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be rejected"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'rejected'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking."""
        booking = self.get_object()
        
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get bookings in calendar event format."""
        queryset = self.get_queryset()
        
        # Convert to FullCalendar event format
        events = []
        for booking in queryset:
            color = {
                'pending': '#ffc107',
                'approved': '#28a745',
                'rejected': '#dc3545',
                'cancelled': '#6c757d',
                'completed': '#17a2b8'
            }.get(booking.status, '#007bff')
            
            events.append({
                'id': booking.id,
                'title': booking.title,
                'start': booking.start_time.isoformat(),
                'end': booking.end_time.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': {
                    'resource': booking.resource.name,
                    'user': booking.user.get_full_name(),
                    'status': booking.status,
                    'description': booking.description,
                }
            })
        
        return Response(events)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get booking statistics."""
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Date range for statistics
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        bookings = Booking.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        stats = {
            'total_bookings': bookings.count(),
            'approved_bookings': bookings.filter(status='approved').count(),
            'pending_bookings': bookings.filter(status='pending').count(),
            'rejected_bookings': bookings.filter(status='rejected').count(),
            'cancelled_bookings': bookings.filter(status='cancelled').count(),
            'bookings_by_resource': list(
                bookings.values('resource__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_user': list(
                bookings.values('user__username', 'user__first_name', 'user__last_name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_group': list(
                bookings.values('user__userprofile__group')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
        }
        
        return Response(stats)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to cancel booking instead of deleting it."""
        booking = self.get_object()
        
        # Check if booking can be cancelled
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark as cancelled instead of deleting
        booking.status = 'cancelled'
        booking.save()
        
        # Create booking history entry
        BookingHistory.objects.create(
            booking=booking,
            user=request.user,
            action='cancelled',
            notes='Cancelled via API'
        )
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def add_prerequisite(self, request, pk=None):
        """Add a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions - only owner or managers can add dependencies
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        dependency_type = request.data.get('dependency_type', 'sequential')
        conditions = request.data.get('conditions', {})
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.select_related('resource', 'user').get(id=prerequisite_id)
            
            # Validate that user has access to prerequisite booking
            if (prerequisite_booking.user != request.user and 
                user_profile.role not in ['technician', 'sysadmin']):
                return Response(
                    {"error": "You don't have access to the specified prerequisite booking"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            booking.add_prerequisite(prerequisite_booking, dependency_type, conditions)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def remove_prerequisite(self, request, pk=None):
        """Remove a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.select_related('resource', 'user').get(id=prerequisite_id)
            booking.prerequisite_bookings.remove(prerequisite_booking)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def dependencies(self, request, pk=None):
        """Get booking dependency information."""
        booking = self.get_object()
        
        prerequisites = []
        for prereq in booking.prerequisite_bookings.select_related('resource', 'user'):
            prerequisites.append({
                'id': prereq.id,
                'title': prereq.title,
                'resource': prereq.resource.name,
                'start_time': prereq.start_time,
                'end_time': prereq.end_time,
                'status': prereq.status,
                'user': prereq.user.get_full_name()
            })
        
        dependents = []
        for dependent in booking.dependent_bookings.select_related('resource', 'user'):
            dependents.append({
                'id': dependent.id,
                'title': dependent.title,
                'resource': dependent.resource.name,
                'start_time': dependent.start_time,
                'end_time': dependent.end_time,
                'status': dependent.status,
                'user': dependent.user.get_full_name(),
                'dependency_type': dependent.dependency_type
            })
        
        return Response({
            'can_start': booking.can_start,
            'dependency_status': booking.dependency_status,
            'dependency_type': booking.dependency_type,
            'dependency_conditions': booking.dependency_conditions,
            'prerequisites': prerequisites,
            'dependents': dependents,
            'blocking_dependencies': [
                {
                    'id': dep.id,
                    'title': dep.title,
                    'status': dep.status,
                    'resource': dep.resource.name
                }
                for dep in booking.get_blocking_dependencies()
            ]
        })
    
    @action(detail=False, methods=['post'])
    def join_waiting_list(self, request):
        """Join waiting list when booking conflicts exist."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # Check if validation failed due to conflicts
            errors = serializer.errors
            if any('conflict' in str(error).lower() for error in errors.values()):
                # Offer to join waiting list
                resource_id = request.data.get('resource_id')
                start_time = request.data.get('start_time')
                end_time = request.data.get('end_time')
                title = request.data.get('title', 'Booking Request')
                description = request.data.get('description', '')
                
                if resource_id and start_time and end_time:
                    waiting_entry = WaitingListEntry.objects.create(
                        user=request.user,
                        resource_id=resource_id,
                        desired_start_time=start_time,
                        desired_end_time=end_time,
                        title=title,
                        description=description,
                        flexible_start=request.data.get('flexible_start', False),
                        flexible_duration=request.data.get('flexible_duration', False),
                        auto_book=request.data.get('auto_book', False)
                    )
                    
                    return Response({
                        'booking_failed': True,
                        'reason': 'time_conflict',
                        'waiting_list_entry': WaitingListEntrySerializer(waiting_entry).data,
                        'message': 'Booking conflicts detected. You have been added to the waiting list.'
                    }, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # If no conflicts, create booking normally
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)