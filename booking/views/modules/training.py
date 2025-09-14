# booking/views/modules/training.py
"""
Training-related views for the Aperture Booking system.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Max
from datetime import datetime, timedelta
import json

from ...models import (
    Resource, Booking, UserProfile, TrainingRequest, UserTraining, TrainingCourse,
    ResourceTrainingRequirement, ResourceResponsible
)
from ...forms import ResourceResponsibleForm


def is_lab_admin(user):
    """Check if user is in Lab Admin group."""
    return user.groups.filter(name='Lab Admin').exists() or user.is_staff or user.userprofile.role in ['technician', 'sysadmin']


@login_required
def training_dashboard_view(request):
    """Dashboard for training management."""
    # User's training statistics
    my_completed_training = UserTraining.objects.filter(
        user=request.user, status='completed'
    ).count()
    
    my_in_progress_training = UserTraining.objects.filter(
        user=request.user, status='in_progress'
    ).count()
    
    available_courses = TrainingCourse.objects.filter(is_active=True).count()
    
    expiring_soon = UserTraining.objects.filter(
        user=request.user,
        status='completed',
        expires_at__lte=timezone.now() + timedelta(days=30)
    ).count()
    
    # User's training progress
    my_training = UserTraining.objects.filter(
        user=request.user
    ).select_related('training_course').order_by('-enrolled_at')[:6]
    
    # Recommended courses (placeholder logic)
    recommended_courses = TrainingCourse.objects.filter(
        is_active=True
    ).exclude(
        id__in=UserTraining.objects.filter(user=request.user).values_list('training_course_id', flat=True)
    )[:5]
    
    # Upcoming sessions
    upcoming_sessions = UserTraining.objects.filter(
        user=request.user,
        session_date__gte=timezone.now(),
        status__in=['enrolled', 'in_progress']
    ).order_by('session_date')[:5]
    
    context = {
        'my_completed_training': my_completed_training,
        'my_in_progress_training': my_in_progress_training,
        'available_courses': available_courses,
        'expiring_soon': expiring_soon,
        'my_training': my_training,
        'recommended_courses': recommended_courses,
        'upcoming_sessions': upcoming_sessions,
    }
    
    return render(request, 'booking/training_dashboard.html', context)


@login_required
def training_redirect_view(request, course_id=None):
    """Redirect training courses URLs to training dashboard."""
    messages.info(request, "Training enrollment has been replaced with scheduled training managed by lab administrators.")
    return redirect('booking:training_dashboard')


@login_required  
def training_course_detail_view(request, course_id):
    """Redirect to training dashboard - course enrollment removed."""
    return training_redirect_view(request, course_id)


@login_required
def enroll_training_view(request, course_id):
    """Redirect to training dashboard - course enrollment removed."""
    return training_redirect_view(request, course_id)




@login_required
def training_and_inductions_view(request):
    """Combined view for training and inductions."""
    from booking.models import AccessRequest, UserRiskAssessment

    # User's induction status
    user_profile = getattr(request.user, 'userprofile', None)
    induction_status = {
        'completed': user_profile.is_inducted if user_profile else False,
        'required': True  # Lab induction is always required
    }

    # Get pending access requests that require induction
    pending_induction_requests = []
    if not induction_status['completed']:
        pending_induction_requests = AccessRequest.objects.filter(
            user=request.user,
            status='pending',
            safety_induction_confirmed=False
        ).select_related('resource')

    # Get training requirements from access requests
    training_requirements = UserTraining.objects.filter(
        user=request.user,
        status__in=['enrolled', 'in_progress', 'scheduled']
    ).select_related('training_course')

    # Get required training from resource access requests
    training_from_access_requests = []
    pending_access_requests = AccessRequest.objects.filter(
        user=request.user,
        status='pending',
        lab_training_confirmed=False
    ).select_related('resource')

    for access_request in pending_access_requests:
        resource = access_request.resource
        # Check if resource has training requirements
        training_reqs = resource.training_requirements.filter(
            is_mandatory=True
        ).select_related('training_course')

        for req in training_reqs:
            # Check if user already has this training
            has_training = UserTraining.objects.filter(
                user=request.user,
                training_course=req.training_course,
                status='completed'
            ).exists()

            if not has_training:
                training_from_access_requests.append({
                    'resource': resource,
                    'training_course': req.training_course,
                    'access_request': access_request
                })

    # Get risk assessment requirements
    risk_assessments = UserRiskAssessment.objects.filter(
        user=request.user,
        status__in=['draft', 'submitted', 'in_review']
    ).select_related('risk_assessment', 'risk_assessment__resource')

    # Get pending risk assessments from access requests
    pending_risk_assessments = []
    for access_request in AccessRequest.objects.filter(
        user=request.user,
        status='pending',
        risk_assessment_confirmed=False
    ).select_related('resource'):
        if access_request.resource.requires_risk_assessment:
            pending_risk_assessments.append({
                'resource': access_request.resource,
                'access_request': access_request
            })

    context = {
        'induction_status': induction_status,
        'pending_induction_requests': pending_induction_requests,
        'training_requirements': training_requirements,
        'training_from_access_requests': training_from_access_requests,
        'risk_assessments': risk_assessments,
        'pending_risk_assessments': pending_risk_assessments,
    }

    return render(request, 'booking/training_and_inductions.html', context)


@login_required
def manage_training_view(request):
    """Manage training (for instructors/managers)."""
    if not request.user.userprofile.role in ['technician', 'academic', 'sysadmin']:
        messages.error(request, "You don't have permission to manage training.")
        return redirect('booking:training_dashboard')
    
    # Get training records to review
    pending_training = UserTraining.objects.filter(
        status='completed'
    ).select_related('user', 'training_course').order_by('-completed_at')
    
    context = {
        'pending_training': pending_training,
    }
    
    return render(request, 'booking/manage_training.html', context)


@login_required
def manage_resource_view(request, resource_id):
    """Manage a specific resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage resources.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    context = {
        'resource': resource,
    }
    
    return render(request, 'booking/manage_resource.html', context)


@login_required
def assign_resource_responsible_view(request, resource_id):
    """Assign responsibility for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to assign resource responsibility.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    if request.method == 'POST':
        form = ResourceResponsibleForm(request.POST, resource=resource)
        if form.is_valid():
            responsible = form.save(commit=False)
            responsible.resource = resource
            responsible.assigned_by = request.user
            responsible.save()
            
            messages.success(request, f"Resource responsibility assigned to {responsible.user.get_full_name()}.")
            return redirect('booking:manage_resource', resource_id=resource_id)
    else:
        form = ResourceResponsibleForm(resource=resource)
    
    context = {
        'resource': resource,
        'form': form,
    }
    
    return render(request, 'booking/assign_resource_responsible.html', context)


@login_required
def resource_training_requirements_view(request, resource_id):
    """Manage training requirements for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage training requirements.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    training_requirements = ResourceTrainingRequirement.objects.filter(
        resource=resource
    ).select_related('training_course').order_by('order')
    
    context = {
        'resource': resource,
        'training_requirements': training_requirements,
    }
    
    return render(request, 'booking/resource_training_requirements.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_training_view(request):
    """Manage training requests and sessions."""
    from booking.models import TrainingRequest, UserTraining, TrainingCourse
    
    # Handle training request actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'complete_training':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            
            # Mark training as completed
            training_request.status = 'completed'
            training_request.completed_date = timezone.now()
            training_request.reviewed_by = request.user
            training_request.reviewed_at = timezone.now()
            training_request.save()
            
            # Update user's training level if this training increased it
            user_profile = training_request.user.userprofile
            if training_request.requested_level > user_profile.training_level:
                user_profile.training_level = training_request.requested_level
                user_profile.save()
            
            # Create UserTraining record if there's a specific course involved
            if hasattr(training_request, 'training_course') and training_request.training_course:
                user_training, created = UserTraining.objects.get_or_create(
                    user=training_request.user,
                    training_course=training_request.training_course,
                    defaults={
                        'status': 'completed',
                        'completed_at': timezone.now(),
                        'enrolled_at': training_request.created_at
                    }
                )
                if not created and user_training.status != 'completed':
                    user_training.status = 'completed'
                    user_training.completed_at = timezone.now()
                    user_training.save()
            
            messages.success(request, f'Training marked as completed for {training_request.user.get_full_name()}. Training level updated to {training_request.requested_level}.')
            
        elif action == 'delete_request':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            user_name = training_request.user.get_full_name()
            
            training_request.delete()
            messages.success(request, f'Training request for {user_name} has been deleted', extra_tags='persistent-alert')
            
        elif action == 'edit_request':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            
            # Parse training date and time
            training_date = request.POST.get('training_date')
            training_time = request.POST.get('training_time')
            training_datetime = None
            
            if training_date and training_time:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date or time format.')
                    return redirect('booking:lab_admin_training')
            elif training_date:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                    return redirect('booking:lab_admin_training')
            
            # Update training request fields
            training_request.training_date = training_datetime
            training_request.justification = request.POST.get('training_justification', training_request.justification)
            training_request.save()
            
            messages.success(request, f'Training request updated for {training_request.user.get_full_name()}', extra_tags='persistent-alert')
            
        elif action == 'schedule_training':
            user_training_id = request.POST.get('user_training_id')
            session_date = request.POST.get('session_date')
            
            if user_training_id and session_date:
                user_training = get_object_or_404(UserTraining, id=user_training_id)
                
                try:
                    # Parse session date and create datetime object
                    session_datetime = datetime.strptime(session_date, "%Y-%m-%d")
                    session_datetime = timezone.make_aware(session_datetime)
                    
                    # Set default training duration (2 hours)
                    training_duration = timedelta(hours=2)
                    session_end_time = session_datetime + training_duration
                    
                    # Find associated resource (from training course requirements)
                    resource = None
                    training_requirements = user_training.training_course.resource_requirements.all()
                    if training_requirements.exists():
                        resource = training_requirements.first().resource
                    
                    if resource:
                        # Check for booking conflicts
                        conflicts = Booking.objects.filter(
                            resource=resource,
                            status__in=['approved', 'pending'],
                            start_time__lt=session_end_time,
                            end_time__gt=session_datetime
                        )
                        
                        if conflicts.exists():
                            # Find next available slot
                            next_slot = None
                            for day_offset in range(1, 30):  # Check next month
                                test_start = session_datetime + timedelta(days=day_offset)
                                test_end = test_start + training_duration
                                
                                test_conflicts = Booking.objects.filter(
                                    resource=resource,
                                    status__in=['approved', 'pending'],
                                    start_time__lt=test_end,
                                    end_time__gt=test_start
                                )
                                
                                if not test_conflicts.exists():
                                    next_slot = test_start
                                    break
                            
                            conflict_msg = f'The requested date conflicts with existing bookings for {resource.name}.'
                            if next_slot:
                                conflict_msg += f' Next available date: {next_slot.strftime("%B %d, %Y")}'
                            
                            messages.warning(request, conflict_msg, extra_tags='persistent-alert')
                        else:
                            # No conflicts, create the booking
                            booking = Booking.objects.create(
                                resource=resource,
                                user=user_training.user,
                                title=f'Training Session: {user_training.training_course.title}',
                                description=f'Training session for {user_training.user.get_full_name()} - {user_training.training_course.title}',
                                start_time=session_datetime,
                                end_time=session_end_time,
                                status='approved',  # Training bookings are auto-approved
                                notes=f'User Training ID: {user_training.id}'
                            )
                            
                            # Update user training
                            user_training.session_date = session_date
                            user_training.instructor = request.user
                            user_training.status = 'scheduled'
                            user_training.save()
                            
                            # Send notifications
                            try:
                                from booking.notifications import training_request_notifications
                                training_request_notifications.training_request_scheduled(user_training, session_datetime)
                            except Exception as e:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.error(f"Failed to send training scheduled notification: {e}")
                            
                            messages.success(request, f'Training session scheduled for {user_training.user.get_full_name()} on {session_datetime.strftime("%B %d, %Y")}. Resource {resource.name} has been booked.', extra_tags='persistent-alert')
                    else:
                        # No specific resource, just update the user training
                        user_training.session_date = session_date
                        user_training.instructor = request.user
                        user_training.status = 'scheduled'
                        user_training.save()
                        
                        # Send notifications
                        try:
                            from booking.notifications import training_request_notifications
                            training_request_notifications.training_request_scheduled(user_training, session_datetime)
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.error(f"Failed to send training scheduled notification: {e}")
                        
                        messages.success(request, f'Training session scheduled for {user_training.user.get_full_name()} on {session_datetime.strftime("%B %d, %Y")}', extra_tags='persistent-alert')
                        
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                except Exception as e:
                    messages.error(request, f'Error scheduling training session: {str(e)}')

        elif action == 'complete_user_training':
            user_training_id = request.POST.get('user_training_id')
            user_training = get_object_or_404(UserTraining, id=user_training_id)

            # Complete the training by admin confirmation
            user_training.mark_as_completed_by_admin(
                instructor=request.user,
                notes=f'Training marked complete by {request.user.get_full_name()}'
            )

            messages.success(request, f'Training marked as completed for {user_training.user.get_full_name()}')

        elif action == 'schedule_legacy_training':
            request_id = request.POST.get('request_id')
            training_date = request.POST.get('training_date')
            training_time = request.POST.get('training_time')
            training_justification = request.POST.get('training_justification', '')

            training_request = get_object_or_404(TrainingRequest, id=request_id)

            # Build datetime from date and time
            training_datetime = None
            if training_date and training_time:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date or time format.')
                    return redirect('booking:lab_admin_training')
            elif training_date:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                    return redirect('booking:lab_admin_training')

            # Update training request fields
            training_request.training_date = training_datetime
            training_request.justification = training_justification
            training_request.save()

            messages.success(request, f'Legacy training request scheduled for {training_request.user.get_full_name()}', extra_tags='persistent-alert')

        elif action == 'cancel_user_training':
            user_training_id = request.POST.get('user_training_id')
            user_training = get_object_or_404(UserTraining, id=user_training_id)

            # Cancel the training
            user_training.status = 'cancelled'
            user_training.save()

            messages.success(request, f'Training cancelled for {user_training.user.get_full_name()}')

        return redirect('booking:lab_admin_training')
    
    # Get training data
    # Get pending UserTraining records (users who need training for resource access)
    pending_requests = UserTraining.objects.filter(
        status='enrolled'
    ).select_related('user', 'training_course')

    # Keep legacy TrainingRequest support for backward compatibility
    legacy_training_requests = TrainingRequest.objects.filter(status='pending').select_related('user', 'resource', 'reviewed_by')

    upcoming_sessions = UserTraining.objects.filter(
        session_date__gte=timezone.now().date(),
        status='scheduled'
    ).select_related('user', 'training_course', 'instructor')
    
    # Get training courses for management
    training_courses = TrainingCourse.objects.all().select_related('created_by').prefetch_related(
        'instructors', 'prerequisite_courses'
    ).order_by('-created_at')
    
    context = {
        'pending_requests': pending_requests,
        'legacy_training_requests': legacy_training_requests,
        'upcoming_sessions': upcoming_sessions,
        'training_courses': training_courses,
    }
    
    return render(request, 'booking/lab_admin_training.html', context)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def add_training_requirement_api(request, resource_id):
    """API endpoint to add a training requirement to a resource."""
    from booking.models import Resource, ResourceTrainingRequirement, TrainingCourse
    import json
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        data = json.loads(request.body)
        
        course_id = data.get('course_id')
        is_mandatory = data.get('is_mandatory', True)
        
        if not course_id:
            return JsonResponse({'error': 'Training course ID is required'}, status=400)
        
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Check if requirement already exists
        if ResourceTrainingRequirement.objects.filter(resource=resource, training_course=course).exists():
            return JsonResponse({'error': 'This training requirement already exists'}, status=400)
        
        # Get the highest order number
        max_order = ResourceTrainingRequirement.objects.filter(resource=resource).aggregate(
            Max('order')
        )['order__max'] or 0
        
        # Create the requirement
        requirement = ResourceTrainingRequirement.objects.create(
            resource=resource,
            training_course=course,
            is_mandatory=is_mandatory,
            order=max_order + 1
        )
        
        return JsonResponse({
            'success': True,
            'requirement': {
                'id': requirement.id,
                'course_title': course.title,
                'course_code': course.code,
                'course_type': course.get_course_type_display(),
                'duration': course.duration_hours,
                'is_mandatory': requirement.is_mandatory,
                'order': requirement.order
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["DELETE"])
def remove_training_requirement_api(request, resource_id, requirement_id):
    """API endpoint to remove a training requirement from a resource."""
    from booking.models import Resource, ResourceTrainingRequirement
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        requirement = get_object_or_404(ResourceTrainingRequirement, id=requirement_id, resource=resource)
        
        # Store the course details before deletion
        course_name = requirement.training_course.title
        course_id = requirement.training_course.id
        course_code = requirement.training_course.code
        
        # Delete the requirement
        requirement.delete()
        
        # Reorder remaining requirements
        remaining_requirements = ResourceTrainingRequirement.objects.filter(
            resource=resource
        ).order_by('order')
        
        for idx, req in enumerate(remaining_requirements, 1):
            req.order = idx
            req.save(update_fields=['order'])
        
        return JsonResponse({
            'success': True,
            'message': f'Training requirement "{course_name}" removed successfully',
            'course_id': course_id,
            'course_code': course_code,
            'course_name': course_name
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def update_training_requirement_order_api(request, resource_id):
    """API endpoint to update the order of training requirements."""
    from booking.models import Resource, ResourceTrainingRequirement
    import json
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        data = json.loads(request.body)
        
        requirement_orders = data.get('requirements', [])
        
        for order_data in requirement_orders:
            requirement_id = order_data.get('id')
            new_order = order_data.get('order')
            
            if requirement_id and new_order is not None:
                ResourceTrainingRequirement.objects.filter(
                    id=requirement_id,
                    resource=resource
                ).update(order=new_order)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def add_training_course_api(request):
    """API endpoint to add a new training course."""
    from booking.models import TrainingCourse
    import json
    
    try:
        # Parse JSON data
        data = json.loads(request.body)
        
        # Validate required fields
        title = data.get('title', '').strip()
        code = data.get('code', '').strip()
        
        if not title:
            return JsonResponse({'error': 'Course title is required'}, status=400)
        
        if not code:
            return JsonResponse({'error': 'Course code is required'}, status=400)
        
        # Check for duplicate code
        if TrainingCourse.objects.filter(code=code).exists():
            return JsonResponse({'error': 'A course with this code already exists'}, status=400)
        
        # Parse numeric fields safely
        try:
            duration_hours = float(data.get('duration_hours', 1.0)) if data.get('duration_hours') else 1.0
        except (ValueError, TypeError):
            duration_hours = 1.0
            
        try:
            max_participants = int(data.get('max_participants', 10)) if data.get('max_participants') else 10
        except (ValueError, TypeError):
            max_participants = 10
            
        try:
            valid_for_months = int(data.get('valid_for_months', 24)) if data.get('valid_for_months') else 24
        except (ValueError, TypeError):
            valid_for_months = 24
            
        try:
            pass_mark_percentage = float(data.get('pass_mark_percentage', 80.0)) if data.get('pass_mark_percentage') else 80.0
        except (ValueError, TypeError):
            pass_mark_percentage = 80.0
        
        # Create the course
        course = TrainingCourse.objects.create(
            title=title,
            code=code,
            description=data.get('description', ''),
            course_type=data.get('course_type', 'equipment'),
            delivery_method=data.get('delivery_method', 'in_person'),
            duration_hours=duration_hours,
            max_participants=max_participants,
            learning_objectives=data.get('learning_objectives', []) if isinstance(data.get('learning_objectives'), list) else [],
            course_materials=data.get('course_materials', []) if isinstance(data.get('course_materials'), list) else [],
            assessment_criteria=data.get('assessment_criteria', []) if isinstance(data.get('assessment_criteria'), list) else [],
            valid_for_months=valid_for_months,
            requires_practical_assessment=data.get('requires_practical_assessment') in ['true', 'True', True, '1', 1, 'on'] if data.get('requires_practical_assessment') is not None else False,
            pass_mark_percentage=pass_mark_percentage,
            is_active=data.get('is_active') not in ['false', 'False', False, '0', 0, 'off', None] if data.get('is_active') is not None else True,
            is_mandatory=data.get('is_mandatory') in ['true', 'True', True, '1', 1, 'on'] if data.get('is_mandatory') is not None else False,
            created_by=request.user,
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{title}" created successfully',
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'course_type': course.get_course_type_display(),
                'delivery_method': course.get_delivery_method_display(),
                'duration_hours': float(course.duration_hours),
                'is_active': course.is_active,
                'created_date': course.created_at.strftime('%Y-%m-%d'),
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST", "PUT"])
def edit_training_course_api(request, course_id):
    """API endpoint to edit an existing training course."""
    from booking.models import TrainingCourse
    import json
    
    try:
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Parse JSON data
        data = json.loads(request.body)
        
        # Validate required fields
        title = data.get('title', '').strip()
        code = data.get('code', '').strip()
        
        if not title:
            return JsonResponse({'error': 'Course title is required'}, status=400)
        
        if not code:
            return JsonResponse({'error': 'Course code is required'}, status=400)
        
        # Check for duplicate code (excluding current course)
        if TrainingCourse.objects.filter(code=code).exclude(id=course_id).exists():
            return JsonResponse({'error': 'A course with this code already exists'}, status=400)
        
        # Parse numeric fields safely
        try:
            duration_hours = float(data.get('duration_hours')) if data.get('duration_hours') else course.duration_hours
        except (ValueError, TypeError):
            duration_hours = course.duration_hours
            
        try:
            max_participants = int(data.get('max_participants')) if data.get('max_participants') else course.max_participants
        except (ValueError, TypeError):
            max_participants = course.max_participants
            
        try:
            valid_for_months = int(data.get('valid_for_months')) if data.get('valid_for_months') else course.valid_for_months
        except (ValueError, TypeError):
            valid_for_months = course.valid_for_months
            
        try:
            pass_mark_percentage = float(data.get('pass_mark_percentage')) if data.get('pass_mark_percentage') else course.pass_mark_percentage
        except (ValueError, TypeError):
            pass_mark_percentage = course.pass_mark_percentage
        
        # Update the course
        course.title = title
        course.code = code
        course.description = data.get('description', course.description)
        course.course_type = data.get('course_type', course.course_type)
        course.delivery_method = data.get('delivery_method', course.delivery_method)
        course.duration_hours = duration_hours
        course.max_participants = max_participants
        course.learning_objectives = data.get('learning_objectives', course.learning_objectives) if isinstance(data.get('learning_objectives'), list) else course.learning_objectives
        course.course_materials = data.get('course_materials', course.course_materials) if isinstance(data.get('course_materials'), list) else course.course_materials
        course.assessment_criteria = data.get('assessment_criteria', course.assessment_criteria) if isinstance(data.get('assessment_criteria'), list) else course.assessment_criteria
        course.valid_for_months = valid_for_months
        course.requires_practical_assessment = data.get('requires_practical_assessment') in ['true', 'True', True, '1', 1, 'on'] if data.get('requires_practical_assessment') is not None else course.requires_practical_assessment
        course.pass_mark_percentage = pass_mark_percentage
        course.is_active = data.get('is_active') not in ['false', 'False', False, '0', 0, 'off', None] if data.get('is_active') is not None else course.is_active
        course.is_mandatory = data.get('is_mandatory') in ['true', 'True', True, '1', 1, 'on'] if data.get('is_mandatory') is not None else course.is_mandatory
        course.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{title}" updated successfully',
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'course_type': course.get_course_type_display(),
                'delivery_method': course.get_delivery_method_display(),
                'duration_hours': float(course.duration_hours),
                'is_active': course.is_active,
                'updated_date': course.updated_at.strftime('%Y-%m-%d %H:%M'),
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["DELETE"])
def delete_training_course_api(request, course_id):
    """API endpoint to delete a training course."""
    from booking.models import TrainingCourse, ResourceTrainingRequirement, UserTraining
    
    try:
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Check if course is being used in any resource requirements
        resource_count = ResourceTrainingRequirement.objects.filter(training_course=course).count()
        if resource_count > 0:
            return JsonResponse({
                'error': f'Cannot delete this course. It is currently required by {resource_count} resource(s).'
            }, status=400)
        
        # Check if users have training records for this course
        user_training_count = UserTraining.objects.filter(training_course=course).count()
        if user_training_count > 0:
            return JsonResponse({
                'error': f'Cannot delete this course. {user_training_count} user(s) have training records for it.'
            }, status=400)
        
        course_title = course.title
        course.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{course_title}" deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)