# booking/views/modules/lab_admin.py
"""
Lab Admin views for the Aperture Booking.

This module handles lab administrator functionality including user management,
resource management, system administration, and maintenance operations.

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
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Max
from django.core.paginator import Paginator
from django.core.cache import cache
from datetime import datetime, timedelta
import json
import csv

from ...models import (
    UserProfile, Resource, Booking, ApprovalRule, Maintenance,
    AccessRequest, TrainingRequest, Faculty, College, Department,
    ResourceAccess, ResourceResponsible, RiskAssessment, UserRiskAssessment,
    TrainingCourse, ResourceTrainingRequirement, UserTraining, ResourceIssue
)
from ...forms import (
    UserProfileForm, ResourceForm, AccessRequestReviewForm, RiskAssessmentForm,
    UserRiskAssessmentForm, TrainingCourseForm, UserTrainingEnrollForm,
    ResourceResponsibleForm, ResourceIssueReportForm, ResourceIssueUpdateForm,
    IssueFilterForm
)
from ...services.licensing import require_license_feature
from ...notifications import notification_service


def is_lab_admin(user):
    """Check if user is in Lab Admin group."""
    return user.groups.filter(name='Lab Admin').exists() or user.is_staff or user.userprofile.role in ['technician', 'sysadmin']


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_dashboard_view(request):
    """Lab Admin dashboard with overview of pending tasks."""
    from booking.models import AccessRequest, TrainingRequest, UserTraining, UserProfile
    from django.utils import timezone
    from datetime import timedelta

    # Get pending items
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    pending_training_requests = TrainingRequest.objects.filter(status='pending').count()

    # Get upcoming training sessions
    upcoming_training = UserTraining.objects.filter(
        session_date__gte=timezone.now().date(),
        status='scheduled'
    ).count()

    # Get recent registrations (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent_registrations = UserProfile.objects.filter(
        user__date_joined__gte=week_ago
    ).count()

    # Get overdue items
    overdue_access_requests = AccessRequest.objects.filter(
        status='pending',
        created_at__lt=timezone.now() - timedelta(days=3)
    ).count()

    # Get induction statistics
    not_inducted_count = UserProfile.objects.filter(is_inducted=False).count()

    context = {
        'pending_access_requests': pending_access_requests,
        'pending_training_requests': pending_training_requests,
        'upcoming_training': upcoming_training,
        'recent_registrations': recent_registrations,
        'overdue_access_requests': overdue_access_requests,
        'not_inducted_count': not_inducted_count,
    }

    return render(request, 'booking/lab_admin_dashboard.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_access_requests_view(request):
    """Manage access requests."""
    from booking.models import AccessRequest, TrainingRequest

    # Handle status updates
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')

        if request_id and action:
            access_request = get_object_or_404(AccessRequest, id=request_id)

            if action == 'approve':
                try:
                    # Double-check prerequisites before approval
                    if not access_request.prerequisites_met():
                        missing = []
                        if not access_request.safety_induction_confirmed:
                            missing.append("Safety Induction")
                        if not access_request.lab_training_confirmed:
                            missing.append("Lab Training")
                        if not access_request.risk_assessment_confirmed:
                            missing.append("Risk Assessment")

                        missing_str = ", ".join(missing)
                        messages.error(request, f'Cannot approve: Missing prerequisites - {missing_str}', extra_tags='persistent-alert')
                    else:
                        access_request.approve(request.user, "Approved via Lab Admin dashboard")
                        messages.success(request, f'Access request approved for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error approving request: {str(e)}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}', extra_tags='persistent-alert')

            elif action == 'reject':
                try:
                    access_request.reject(request.user, "Rejected via Lab Admin dashboard")
                    messages.success(request, f'Access request rejected for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error rejecting request: {str(e)}')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}')

            elif action == 'confirm_safety':
                notes = request.POST.get('safety_notes', '').strip()
                try:
                    access_request.confirm_safety_induction(request.user, notes)
                    messages.success(request, f'Safety induction confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming safety induction: {str(e)}')

            elif action == 'confirm_training':
                notes = request.POST.get('training_notes', '').strip()
                try:
                    access_request.confirm_lab_training(request.user, notes)
                    messages.success(request, f'Lab training confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming lab training: {str(e)}')

            elif action == 'confirm_risk_assessment':
                notes = request.POST.get('risk_assessment_notes', '').strip()
                try:
                    access_request.confirm_risk_assessment(request.user, notes)
                    messages.success(request, f'Risk assessment confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming risk assessment: {str(e)}')

            elif action == 'schedule_training':
                justification = request.POST.get('training_justification', '').strip()
                training_date = request.POST.get('training_date', '').strip()
                training_time = request.POST.get('training_time', '').strip()
                training_duration = request.POST.get('training_duration', '').strip()
                trainer_notes = request.POST.get('trainer_notes', '').strip()

                if not justification:
                    justification = f"Training requested for access to {access_request.resource.name}"

                # Parse training date and time
                training_datetime = None
                if training_date and training_time:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date or time format.')
                        return redirect('booking:lab_admin_access_requests')
                elif training_date:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date format.')
                        return redirect('booking:lab_admin_access_requests')

                # Add duration and trainer notes to justification if provided
                full_justification = justification
                if training_duration:
                    duration_text = f"{training_duration} hour{'s' if float(training_duration) != 1 else ''}"
                    full_justification += f"\n\nExpected Duration: {duration_text}"
                if trainer_notes:
                    full_justification += f"\n\nTrainer Notes: {trainer_notes}"

                try:
                    # Check if training request already exists for this user and resource with active status
                    existing_request = TrainingRequest.objects.filter(
                        user=access_request.user,
                        resource=access_request.resource,
                        status__in=['pending', 'scheduled']
                    ).first()

                    if existing_request:
                        # Update existing request with new details
                        existing_request.justification = full_justification
                        if training_datetime:
                            existing_request.training_date = training_datetime
                            existing_request.status = 'scheduled'
                        existing_request.save()
                        training_request = existing_request
                        created = False
                    else:
                        # Create new training request with appropriate status
                        initial_status = 'scheduled' if training_datetime else 'pending'
                        training_request = TrainingRequest.objects.create(
                            user=access_request.user,
                            resource=access_request.resource,
                            status=initial_status,
                            requested_level=access_request.resource.required_training_level or 1,
                            current_level=access_request.user.userprofile.training_level,
                            justification=full_justification,
                            training_date=training_datetime
                        )
                        created = True

                    # Handle booking creation and notifications when training is scheduled
                    if training_datetime:
                        try:
                            # Calculate end time (default 2 hours if no duration specified)
                            duration_hours = 2  # Default duration
                            if training_duration:
                                try:
                                    duration_hours = float(training_duration)
                                except ValueError:
                                    duration_hours = 2

                            training_end_time = training_datetime + timedelta(hours=duration_hours)

                            # Check for booking conflicts
                            conflicts = Booking.objects.filter(
                                resource=access_request.resource,
                                status__in=['approved', 'pending'],
                                start_time__lt=training_end_time,
                                end_time__gt=training_datetime
                            )

                            if conflicts.exists():
                                # Find next available slot
                                next_slot = None
                                for hour_offset in range(1, 168):  # Check next week
                                    test_start = training_datetime + timedelta(hours=hour_offset)
                                    test_end = test_start + timedelta(hours=duration_hours)

                                    test_conflicts = Booking.objects.filter(
                                        resource=access_request.resource,
                                        status__in=['approved', 'pending'],
                                        start_time__lt=test_end,
                                        end_time__gt=test_start
                                    )

                                    if not test_conflicts.exists():
                                        next_slot = test_start
                                        break

                                conflict_msg = f'The requested time slot conflicts with existing bookings.'
                                if next_slot:
                                    conflict_msg += f' Next available slot: {next_slot.strftime("%B %d, %Y at %I:%M %p")}'

                                messages.warning(request, conflict_msg, extra_tags='persistent-alert')
                                # Reset to pending status and clear training_date
                                training_request.status = 'pending'
                                training_request.training_date = None
                                training_request.save()
                            else:
                                # No conflicts, create the booking
                                booking = Booking.objects.create(
                                    resource=access_request.resource,
                                    user=access_request.user,
                                    title=f'Training Session: {access_request.resource.name}',
                                    description=f'Training session for {access_request.user.get_full_name()}.\n\n{training_request.justification}',
                                    start_time=training_datetime,
                                    end_time=training_end_time,
                                    status='approved',  # Training bookings are auto-approved
                                    notes=f'Training Request ID: {training_request.id}'
                                )

                                # Send notifications
                                try:
                                    from booking.notifications import training_request_notifications
                                    training_request_notifications.training_request_scheduled(training_request, training_datetime)
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Failed to send training scheduled notification: {e}")

                                if created:
                                    messages.success(request, f'Training session scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')
                                else:
                                    messages.success(request, f'Training session updated and scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')

                        except Exception as e:
                            messages.error(request, f'Error scheduling training session: {str(e)}')
                            # Reset to pending status
                            training_request.status = 'pending'
                            training_request.training_date = None
                            training_request.save()
                    else:
                        # No specific time scheduled
                        if created:
                            messages.success(request, f'Training request created for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                        else:
                            messages.info(request, f'Training request already exists for {access_request.user.get_full_name()}', extra_tags='persistent-alert')

                except Exception as e:
                    messages.error(request, f'Error creating training request: {str(e)}')

        return redirect('booking:lab_admin_access_requests')

    # Get access requests
    access_requests = AccessRequest.objects.select_related(
        'user', 'resource', 'reviewed_by', 'safety_induction_confirmed_by', 'lab_training_confirmed_by', 'risk_assessment_confirmed_by'
    ).order_by('-created_at')

    # Apply filters
    status_filter = request.GET.get('status', 'pending')
    if status_filter and status_filter != 'all':
        access_requests = access_requests.filter(status=status_filter)

    # Pagination
    paginator = Paginator(access_requests, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Add prerequisite status to each request
    for request_obj in page_obj:
        request_obj.prerequisite_status = request_obj.get_prerequisite_status()

    # Add today's date for date picker minimum value
    from datetime import date

    context = {
        'access_requests': page_obj,
        'status_filter': status_filter,
        'today': date.today(),
    }

    return render(request, 'booking/lab_admin_access_requests.html', context)


@login_required


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

        return redirect('booking:lab_admin_training')

    # Get training data
    pending_requests = TrainingRequest.objects.filter(status='pending').select_related('user', 'resource', 'reviewed_by')
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
        'upcoming_sessions': upcoming_sessions,
        'training_courses': training_courses,
    }

    return render(request, 'booking/lab_admin_training.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_risk_assessments_view(request):
    """Manage user risk assessments."""
    from booking.models import UserRiskAssessment, RiskAssessment

    # Handle risk assessment actions
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve_assessment':
            assessment_id = request.POST.get('assessment_id')
            user_assessment = get_object_or_404(UserRiskAssessment, id=assessment_id)

            user_assessment.status = 'approved'
            user_assessment.completed_at = timezone.now()
            user_assessment.save()

            messages.success(request, f'Risk assessment approved for {user_assessment.user.get_full_name()}')

        elif action == 'reject_assessment':
            assessment_id = request.POST.get('assessment_id')
            user_assessment = get_object_or_404(UserRiskAssessment, id=assessment_id)
            rejection_reason = request.POST.get('rejection_reason', '')

            user_assessment.status = 'rejected'
            user_assessment.rejection_reason = rejection_reason
            user_assessment.save()

            messages.success(request, f'Risk assessment rejected for {user_assessment.user.get_full_name()}')

        elif action == 'view_details':
            assessment_id = request.POST.get('assessment_id')
            # This could redirect to a detailed view of the assessment
            return redirect('booking:lab_admin_risk_assessments')

        return redirect('booking:lab_admin_risk_assessments')

    # Get risk assessment data
    submitted_assessments = UserRiskAssessment.objects.filter(
        status='submitted'
    ).select_related('user', 'risk_assessment').order_by('-submitted_at')

    approved_assessments = UserRiskAssessment.objects.filter(
        status='approved'
    ).select_related('user', 'risk_assessment').order_by('-completed_at')[:20]  # Show recent 20

    rejected_assessments = UserRiskAssessment.objects.filter(
        status='rejected'
    ).select_related('user', 'risk_assessment').order_by('-submitted_at')[:20]  # Show recent 20

    context = {
        'submitted_assessments': submitted_assessments,
        'approved_assessments': approved_assessments,
        'rejected_assessments': rejected_assessments,
    }

    return render(request, 'booking/lab_admin_risk_assessments.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_view(request):
    """Manage user profiles and access."""
    from booking.models import UserProfile, ResourceAccess

    # Get users
    users = User.objects.select_related('userprofile').order_by('username')

    # Apply filters
    is_active_filter = request.GET.get('is_active')
    role_filter = request.GET.get('role')
    search_query = request.GET.get('search')

    # Clean up empty values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None

    if is_active_filter == 'true':
        users = users.filter(is_active=True)
    elif is_active_filter == 'false':
        users = users.filter(is_active=False)

    if role_filter:
        users = users.filter(userprofile__role=role_filter)

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get role choices for filter
    role_choices = UserProfile.ROLE_CHOICES

    context = {
        'users': page_obj,
        'is_active_filter': is_active_filter,
        'role_filter': role_filter,
        'search_query': search_query,
        'role_choices': role_choices,
    }

    return render(request, 'booking/lab_admin_users.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_detail_view(request, user_id):
    """Get user details for viewing."""
    try:
        user = User.objects.select_related('userprofile').get(id=user_id)

        # Prepare user data
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        }

        if hasattr(user, 'userprofile'):
            user_data.update({
                'role': user.userprofile.role,
                'phone': user.userprofile.phone,
                'department': user.userprofile.department.name if user.userprofile.department else None,
                'email_verified': user.userprofile.email_verified,
                'is_inducted': user.userprofile.is_inducted,
            })

        # Render HTML for modal
        html = f"""
        <div class="row">
            <div class="col-md-6">
                <h6>Basic Information</h6>
                <dl class="row">
                    <dt class="col-sm-4">Username:</dt>
                    <dd class="col-sm-8">{user.username}</dd>
                    <dt class="col-sm-4">Full Name:</dt>
                    <dd class="col-sm-8">{user.get_full_name() or '-'}</dd>
                    <dt class="col-sm-4">Email:</dt>
                    <dd class="col-sm-8">{user.email}</dd>
                    <dt class="col-sm-4">Status:</dt>
                    <dd class="col-sm-8">
                        {'<span class="badge bg-success">Active</span>' if user.is_active else '<span class="badge bg-danger">Inactive</span>'}
                    </dd>
                </dl>
            </div>
            <div class="col-md-6">
                <h6>Profile Information</h6>
                <dl class="row">
                    <dt class="col-sm-4">Role:</dt>
                    <dd class="col-sm-8">{user.userprofile.get_role_display() if hasattr(user, 'userprofile') else '-'}</dd>
                    <dt class="col-sm-4">Department:</dt>
                    <dd class="col-sm-8">{user_data.get('department', '-')}</dd>
                    <dt class="col-sm-4">Phone:</dt>
                    <dd class="col-sm-8">{user_data.get('phone', '-')}</dd>
                    <dt class="col-sm-4">Email Verified:</dt>
                    <dd class="col-sm-8">
                        {'<span class="badge bg-success">Yes</span>' if user_data.get('email_verified') else '<span class="badge bg-warning text-dark">No</span>'}
                    </dd>
                </dl>
            </div>
        </div>
        <hr>
        <div class="row">
            <div class="col-12">
                <h6>Account Activity</h6>
                <dl class="row">
                    <dt class="col-sm-3">Date Joined:</dt>
                    <dd class="col-sm-9">{user.date_joined.strftime('%B %d, %Y at %I:%M %p')}</dd>
                    <dt class="col-sm-3">Last Login:</dt>
                    <dd class="col-sm-9">{user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'Never'}</dd>
                </dl>
            </div>
        </div>
        """

        return JsonResponse({
            'success': True,
            'user': user_data,
            'html': html
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_edit_view(request, user_id):
    """Edit user details."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        user = User.objects.get(id=user_id)

        # Update user fields
        user.username = request.POST.get('username', user.username)
        user.email = request.POST.get('email', user.email)
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.is_active = request.POST.get('is_active') == 'on'
        user.save()

        # Update or create user profile
        if hasattr(user, 'userprofile'):
            profile = user.userprofile
        else:
            from booking.models import UserProfile
            profile = UserProfile(user=user)

        profile.role = request.POST.get('role', profile.role)
        profile.phone = request.POST.get('phone', profile.phone)
        profile.save()

        messages.success(request, f'User {user.username} updated successfully.')
        return JsonResponse({'success': True})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_delete_view(request, user_id):
    """Delete a user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        from django.db import transaction
        from booking.models import Booking, ResourceAccess, TrainingRequest, RiskAssessment

        user = User.objects.get(id=user_id)

        # Don't allow deleting superusers
        if user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Cannot delete superuser accounts'})

        # Don't allow self-deletion
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'error': 'Cannot delete your own account'})

        # Check for related data
        related_data = []

        # Check for active bookings
        active_bookings = Booking.objects.filter(user=user, status__in=['pending', 'approved']).count()
        if active_bookings > 0:
            related_data.append(f'{active_bookings} active booking(s)')

        # Check for resource access
        resource_access = ResourceAccess.objects.filter(user=user).count()
        if resource_access > 0:
            related_data.append(f'{resource_access} resource access permission(s)')

        # Check for training requests
        training_requests = TrainingRequest.objects.filter(user=user).count()
        if training_requests > 0:
            related_data.append(f'{training_requests} training request(s)')

        # Check for risk assessments
        try:
            risk_assessments = RiskAssessment.objects.filter(created_by=user).count()
            if risk_assessments > 0:
                related_data.append(f'{risk_assessments} risk assessment(s)')
        except:
            # Model might not exist or have different fields
            pass

        # Check for other important relationships
        from booking.models import AccessRequest, WaitingListEntry

        access_requests = AccessRequest.objects.filter(user=user).count()
        if access_requests > 0:
            related_data.append(f'{access_requests} access request(s)')

        waiting_list = WaitingListEntry.objects.filter(user=user).count()
        if waiting_list > 0:
            related_data.append(f'{waiting_list} waiting list entries')

        if related_data:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete user. They have: {", ".join(related_data)}. Please reassign or remove these items first.'
            })

        username = user.username

        # Use transaction to ensure all deletions succeed or none do
        with transaction.atomic():
            # Delete user profile if exists
            if hasattr(user, 'userprofile'):
                user.userprofile.delete()

            # Delete the user
            user.delete()

        messages.success(request, f'User {username} has been deleted.')
        return JsonResponse({'success': True})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        # For debugging, let's provide more detail about the constraint error
        error_msg = str(e)
        if 'FOREIGN KEY constraint failed' in error_msg:
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete user due to existing data dependencies. Please contact system administrator to review user data.'
            })
        return JsonResponse({'success': False, 'error': error_msg})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_toggle_view(request, user_id):
    """Toggle user active status."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        user = User.objects.get(id=user_id)

        # Don't allow toggling superusers
        if user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Cannot modify superuser accounts'})

        # Don't allow self-deactivation
        if user.id == request.user.id and not json.loads(request.body).get('active', True):
            return JsonResponse({'success': False, 'error': 'Cannot deactivate your own account'})

        data = json.loads(request.body)
        user.is_active = data.get('active', True)
        user.save()

        action = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User {user.username} has been {action}.')
        return JsonResponse({'success': True})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_add_view(request):
    """Add a new user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        from django.contrib.auth.forms import UserCreationForm
        from booking.models import UserProfile

        # Validate passwords match
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        if password1 != password2:
            return JsonResponse({'success': False, 'error': 'Passwords do not match'})

        # Check if username already exists
        username = request.POST.get('username')
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Username already exists'})

        # Create user
        user = User.objects.create_user(
            username=username,
            email=request.POST.get('email'),
            password=password1,
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
        )
        user.is_active = request.POST.get('is_active') == 'on'
        user.save()

        # Create user profile
        UserProfile.objects.create(
            user=user,
            role=request.POST.get('role'),
            phone=request.POST.get('phone', ''),
        )

        messages.success(request, f'User {user.username} created successfully.')
        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_bulk_import_view(request):
    """Bulk import users from CSV."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        import csv
        from io import StringIO
        from booking.models import UserProfile

        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})

        # Check file size
        if csv_file.size > 5 * 1024 * 1024:  # 5MB limit
            return JsonResponse({'success': False, 'error': 'File too large (max 5MB)'})

        # Read CSV with better error handling
        try:
            file_data = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                file_data = csv_file.read().decode('latin-1')
            except:
                return JsonResponse({'success': False, 'error': 'Unable to decode file. Please ensure it\'s a valid UTF-8 or Latin-1 encoded CSV file.'})

        # Parse CSV
        try:
            csv_reader = csv.DictReader(StringIO(file_data))
            rows = list(csv_reader)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Invalid CSV format: {str(e)}'})

        if not rows:
            return JsonResponse({'success': False, 'error': 'CSV file is empty or has no data rows'})

        # Check required columns
        required_columns = ['username']
        first_row = rows[0]
        missing_columns = [col for col in required_columns if col not in first_row]
        if missing_columns:
            return JsonResponse({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}. Available columns: {", ".join(first_row.keys())}'
            })

        created = 0
        updated = 0
        errors = []
        row_num = 1  # Start from 1 (header is row 0)

        for row in rows:
            row_num += 1
            try:
                username = row.get('username', '').strip()
                if not username:
                    errors.append(f'Row {row_num}: Missing username')
                    continue

                email = row.get('email', '').strip()
                first_name = row.get('first_name', '').strip()
                last_name = row.get('last_name', '').strip()
                role = row.get('role', 'researcher').strip()

                if User.objects.filter(username=username).exists():
                    if request.POST.get('update_existing') == 'on':
                        user = User.objects.get(username=username)

                        # Update user fields
                        if email:
                            user.email = email
                        if first_name:
                            user.first_name = first_name
                        if last_name:
                            user.last_name = last_name
                        user.save()

                        # Update or create profile
                        if hasattr(user, 'userprofile'):
                            if role:
                                user.userprofile.role = role
                                user.userprofile.save()
                        else:
                            UserProfile.objects.create(
                                user=user,
                                role=role,
                            )

                        updated += 1
                    else:
                        errors.append(f'Row {row_num}: User {username} already exists')
                else:
                    # Create new user
                    from django.contrib.auth.models import make_password
                    import secrets
                    import string

                    # Generate random password
                    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                    )

                    # Create user profile (use get_or_create to avoid duplicates)
                    profile, created_profile = UserProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'role': role,
                            'phone': '',  # Default empty phone
                            'is_inducted': False,
                            'email_verified': False,
                        }
                    )

                    # If profile existed, update the role
                    if not created_profile and role:
                        profile.role = role
                        profile.save()

                    created += 1

            except Exception as e:
                errors.append(f'Row {row_num}: Error processing - {str(e)}')

        # Prepare response
        response_data = {
            'success': True,
            'created': created,
            'updated': updated,
        }

        if errors:
            response_data['errors'] = errors
            response_data['message'] = f'Processed with {len(errors)} error(s)'

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Import failed: {str(e)}'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_bulk_action_view(request):
    """Perform bulk actions on multiple users."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        from django.db import transaction

        data = json.loads(request.body)
        action = data.get('action')
        user_ids = data.get('user_ids', [])

        if not action or not user_ids:
            return JsonResponse({'success': False, 'error': 'Missing action or user IDs'})

        if action not in ['activate', 'deactivate', 'delete']:
            return JsonResponse({'success': False, 'error': 'Invalid action'})

        # Get users (exclude superusers and current user for safety)
        users = User.objects.filter(
            id__in=user_ids,
            is_superuser=False
        ).exclude(id=request.user.id)

        if not users.exists():
            return JsonResponse({'success': False, 'error': 'No valid users found'})

        processed = 0
        errors = []

        with transaction.atomic():
            for user in users:
                try:
                    if action == 'activate':
                        user.is_active = True
                        user.save()
                        processed += 1

                    elif action == 'deactivate':
                        user.is_active = False
                        user.save()
                        processed += 1

                    elif action == 'delete':
                        # Check for dependencies like we do in single delete
                        from booking.models import Booking, ResourceAccess, TrainingRequest, AccessRequest, WaitingListEntry

                        # Check for blocking relationships
                        active_bookings = Booking.objects.filter(user=user, status__in=['pending', 'approved']).count()
                        if active_bookings > 0:
                            errors.append(f'{user.username}: Has {active_bookings} active booking(s)')
                            continue

                        resource_access = ResourceAccess.objects.filter(user=user).count()
                        if resource_access > 0:
                            errors.append(f'{user.username}: Has {resource_access} resource access permission(s)')
                            continue

                        training_requests = TrainingRequest.objects.filter(user=user).count()
                        if training_requests > 0:
                            errors.append(f'{user.username}: Has {training_requests} training request(s)')
                            continue

                        access_requests = AccessRequest.objects.filter(user=user).count()
                        if access_requests > 0:
                            errors.append(f'{user.username}: Has {access_requests} access request(s)')
                            continue

                        waiting_list = WaitingListEntry.objects.filter(user=user).count()
                        if waiting_list > 0:
                            errors.append(f'{user.username}: Has {waiting_list} waiting list entries')
                            continue

                        # Safe to delete
                        if hasattr(user, 'userprofile'):
                            user.userprofile.delete()
                        user.delete()
                        processed += 1

                except Exception as e:
                    errors.append(f'{user.username}: {str(e)}')

        # Create success message
        messages.success(request, f'Bulk {action} completed: {processed} user(s) processed')

        response_data = {
            'success': True,
            'processed': processed,
            'action': action
        }

        if errors:
            response_data['errors'] = errors

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Bulk action failed: {str(e)}'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_export_view(request):
    """Export users to CSV."""
    import csv
    from django.http import HttpResponse

    # Create response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users_export.csv"'

    # Get filtered users
    users = User.objects.select_related('userprofile').order_by('username')

    # Apply filters
    is_active_filter = request.GET.get('is_active')
    if is_active_filter == 'true':
        users = users.filter(is_active=True)
    elif is_active_filter == 'false':
        users = users.filter(is_active=False)

    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(userprofile__role=role_filter)

    search_query = request.GET.get('search')
    # Clean up empty values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # Write CSV
    writer = csv.writer(response)
    writer.writerow(['username', 'email', 'first_name', 'last_name', 'role', 'department', 'is_active', 'email_verified', 'date_joined'])

    for user in users:
        writer.writerow([
            user.username,
            user.email,
            user.first_name,
            user.last_name,
            user.userprofile.get_role_display() if hasattr(user, 'userprofile') else '',
            user.userprofile.department.name if hasattr(user, 'userprofile') and user.userprofile.department else '',
            'Yes' if user.is_active else 'No',
            'Yes' if hasattr(user, 'userprofile') and user.userprofile.email_verified else 'No',
            user.date_joined.strftime('%Y-%m-%d'),
        ])

    return response


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resources_view(request):
    """Manage resources - list, add, edit, delete."""
    from booking.models import Resource

    # Get resources
    resources = Resource.objects.all().order_by('name')

    # Apply filters
    resource_type_filter = request.GET.get('type')
    search_query = request.GET.get('search')
    status_filter = request.GET.get('status', 'all')

    # Clean up empty search values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None

    if resource_type_filter:
        resources = resources.filter(resource_type=resource_type_filter)

    if search_query:
        resources = resources.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(location__icontains=search_query)
        )

    if status_filter == 'active':
        resources = resources.filter(is_active=True)
    elif status_filter == 'inactive':
        resources = resources.filter(is_active=False)

    # Pagination
    paginator = Paginator(resources, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get resource type choices for filter
    resource_types = Resource.RESOURCE_TYPES

    context = {
        'resources': page_obj,
        'resource_type_filter': resource_type_filter,
        'search_query': search_query,
        'status_filter': status_filter,
        'resource_types': resource_types,
    }

    return render(request, 'booking/lab_admin_resources.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resources_bulk_import_view(request):
    """Bulk import resources from CSV."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        import csv
        from io import StringIO
        from booking.models import Resource

        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})

        # Check file size
        if csv_file.size > 5 * 1024 * 1024:  # 5MB limit
            return JsonResponse({'success': False, 'error': 'File too large (max 5MB)'})

        # Read CSV with better error handling
        try:
            file_data = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                file_data = csv_file.read().decode('latin-1')
            except:
                return JsonResponse({'success': False, 'error': 'Unable to decode file. Please ensure it\'s a valid UTF-8 or Latin-1 encoded CSV file.'})

        # Parse CSV
        try:
            csv_reader = csv.DictReader(StringIO(file_data))
            rows = list(csv_reader)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Invalid CSV format: {str(e)}'})

        if not rows:
            return JsonResponse({'success': False, 'error': 'CSV file is empty or has no data rows'})

        # Check required columns
        required_columns = ['name', 'resource_type']
        first_row = rows[0]
        missing_columns = [col for col in required_columns if col not in first_row]
        if missing_columns:
            return JsonResponse({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}. Available columns: {", ".join(first_row.keys())}'
            })

        # Valid resource types
        valid_resource_types = [choice[0] for choice in Resource.RESOURCE_TYPES]

        created = 0
        updated = 0
        errors = []
        row_num = 1  # Start from 1 (header is row 0)

        for row in rows:
            row_num += 1
            try:
                name = row.get('name', '').strip()
                if not name:
                    errors.append(f'Row {row_num}: Missing name')
                    continue

                resource_type = row.get('resource_type', '').strip().lower()
                if not resource_type:
                    errors.append(f'Row {row_num}: Missing resource_type')
                    continue

                if resource_type not in valid_resource_types:
                    errors.append(f'Row {row_num}: Invalid resource_type "{resource_type}". Valid types: {", ".join(valid_resource_types)}')
                    continue

                description = row.get('description', '').strip()
                location = row.get('location', '').strip()
                capacity_str = row.get('capacity', '').strip()
                is_active_str = row.get('is_active', 'true').strip().lower()

                # Parse capacity
                capacity = 1  # default
                if capacity_str:
                    try:
                        capacity = int(capacity_str)
                        if capacity < 1:
                            capacity = 1
                    except ValueError:
                        errors.append(f'Row {row_num}: Invalid capacity "{capacity_str}", using default of 1')
                        capacity = 1

                # Parse is_active
                is_active = is_active_str in ['true', '1', 'yes', 'active']

                if Resource.objects.filter(name=name).exists():
                    if request.POST.get('update_existing') == 'on':
                        resource = Resource.objects.get(name=name)

                        # Update resource fields
                        resource.resource_type = resource_type
                        if description:
                            resource.description = description
                        if location:
                            resource.location = location
                        resource.capacity = capacity
                        resource.is_active = is_active
                        resource.save()

                        updated += 1
                    else:
                        errors.append(f'Row {row_num}: Resource "{name}" already exists')
                else:
                    # Create new resource
                    resource = Resource.objects.create(
                        name=name,
                        resource_type=resource_type,
                        description=description,
                        location=location,
                        capacity=capacity,
                        is_active=is_active,
                    )

                    created += 1

            except Exception as e:
                errors.append(f'Row {row_num}: Error processing - {str(e)}')

        # Prepare response
        response_data = {
            'success': True,
            'created': created,
            'updated': updated,
        }

        if errors:
            response_data['errors'] = errors
            response_data['message'] = f'Processed with {len(errors)} error(s)'

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Import failed: {str(e)}'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_add_resource_view(request):
    """Add a new resource."""
    from booking.models import Resource
    from ..forms import ResourceForm

    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f'Resource "{resource.name}" has been created successfully.')
            return redirect('booking:lab_admin_resources')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceForm()

    context = {
        'form': form,
        'title': 'Add New Resource',
        'action': 'Add',
    }

    return render(request, 'booking/lab_admin_resource_form.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_edit_resource_view(request, resource_id):
    """Edit an existing resource."""
    from booking.models import Resource, ResourceTrainingRequirement, TrainingCourse
    from ..forms import ResourceForm

    resource = get_object_or_404(Resource, id=resource_id)

    if request.method == 'POST':
        # Handle regular form submission
        form = ResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f'Resource "{resource.name}" has been updated successfully.')
            return redirect('booking:lab_admin_resources')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceForm(instance=resource)

    # Get current training requirements for this resource
    training_requirements = ResourceTrainingRequirement.objects.filter(
        resource=resource
    ).select_related('training_course').order_by('order')

    # Get all active training courses for the dropdown
    available_courses = TrainingCourse.objects.filter(is_active=True).order_by('title')

    # Get IDs of courses already assigned to this resource
    assigned_course_ids = training_requirements.values_list('training_course_id', flat=True)

    context = {
        'form': form,
        'resource': resource,
        'title': f'Edit Resource: {resource.name}',
        'action': 'Update',
        'training_requirements': training_requirements,
        'available_courses': available_courses,
        'assigned_course_ids': list(assigned_course_ids),
    }

    return render(request, 'booking/lab_admin_resource_form.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_delete_resource_view(request, resource_id):
    """Delete a resource with confirmation."""
    from booking.models import Resource

    resource = get_object_or_404(Resource, id=resource_id)

    if request.method == 'POST':
        # Check if resource has any bookings
        if resource.bookings.exists():
            messages.error(request, f'Cannot delete "{resource.name}" because it has existing bookings. Please deactivate it instead.')
            return redirect('booking:lab_admin_resources')

        resource_name = resource.name
        resource.delete()
        messages.success(request, f'Resource "{resource_name}" has been deleted successfully.')
        return redirect('booking:lab_admin_resources')

    # Check dependencies
    booking_count = resource.bookings.count()
    access_count = resource.access_permissions.count()

    context = {
        'resource': resource,
        'booking_count': booking_count,
        'access_count': access_count,
        'can_delete': booking_count == 0,
    }

    return render(request, 'booking/lab_admin_resource_delete.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_close_resource_view(request, resource_id):
    """Close a resource to prevent new bookings."""
    from booking.models import Resource

    resource = get_object_or_404(Resource, id=resource_id)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        resource.close_resource(request.user, reason)
        messages.success(request, f'Resource "{resource.name}" has been closed to prevent new bookings.')
        return redirect('booking:lab_admin_resources')

    context = {
        'resource': resource,
    }

    return render(request, 'booking/lab_admin_resource_close.html', context)


@login_required
@user_passes_test(is_lab_admin)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def lab_admin_open_resource_view(request, resource_id):
    """Reopen a closed resource for bookings."""
    from booking.models import Resource

    resource = get_object_or_404(Resource, id=resource_id)
    resource.open_resource()
    messages.success(request, f'Resource "{resource.name}" has been reopened for bookings.')
    return redirect('booking:lab_admin_resources')


@login_required
@user_passes_test(is_lab_admin)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resource_checklist_view(request, resource_id):
    """Manage checklist items for a resource."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from booking.models import Resource, ChecklistItem, ResourceChecklistItem
    from ..forms import ResourceChecklistConfigForm
    from django.utils import timezone

    resource = get_object_or_404(Resource, id=resource_id)

    if request.method == 'POST':
        form = ResourceChecklistConfigForm(resource, request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Checklist configuration updated for "{resource.name}".')
                return redirect('booking:lab_admin_resource_checklist', resource_id=resource.id)
            except Exception as e:
                messages.error(request, f'Error updating checklist: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceChecklistConfigForm(resource)

    # Get available checklist items grouped by category
    available_items = ChecklistItem.objects.all().order_by('category', 'title')
    items_by_category = {}
    for item in available_items:
        category = item.get_category_display()
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)

    # Get currently assigned items
    assigned_items = ResourceChecklistItem.objects.filter(
        resource=resource,
        is_active=True
    ).select_related('checklist_item').order_by('order', 'checklist_item__category')

    context = {
        'resource': resource,
        'form': form,
        'items_by_category': items_by_category,
        'assigned_items': assigned_items,
        'total_available': available_items.count(),
        'total_assigned': assigned_items.count(),
    }

    return render(request, 'booking/lab_admin_resource_checklist.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_maintenance_view(request):
    """Display and manage maintenance periods for lab administrators."""
    from django.core.paginator import Paginator
    from django.utils import timezone

    # Get filter parameters
    resource_filter = request.GET.get('resource', '')
    type_filter = request.GET.get('type', '')
    search_query = request.GET.get('search', '')

    # Base queryset
    maintenance_list = Maintenance.objects.select_related('resource', 'created_by').order_by('-start_time')

    # Apply filters
    if resource_filter:
        maintenance_list = maintenance_list.filter(resource_id=resource_filter)

    if type_filter:
        maintenance_list = maintenance_list.filter(maintenance_type=type_filter)

    if search_query:
        maintenance_list = maintenance_list.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(resource__name__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(maintenance_list, 25)
    page_number = request.GET.get('page')
    maintenance_periods = paginator.get_page(page_number)

    # Statistics
    now = timezone.now()
    stats = {
        'scheduled_count': Maintenance.objects.filter(start_time__gt=now).count(),
        'active_count': Maintenance.objects.filter(start_time__lte=now, end_time__gte=now).count(),
        'completed_count': Maintenance.objects.filter(
            end_time__lt=now,
            start_time__month=now.month,
            start_time__year=now.year
        ).count(),
        'recurring_count': Maintenance.objects.filter(is_recurring=True).count(),
    }

    # Get all resources for filtering
    resources = Resource.objects.filter(is_active=True).order_by('name')

    context = {
        'maintenance_periods': maintenance_periods,
        'resources': resources,
        'stats': stats,
        'resource_filter': resource_filter,
        'type_filter': type_filter,
        'search_query': search_query,
    }

    return render(request, 'booking/lab_admin_maintenance.html', context)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_add_maintenance_view(request):
    """Add a new maintenance period."""
    import json
    from django.utils.dateparse import parse_datetime

    if request.method == 'POST':
        try:
            # Get form data
            title = request.POST.get('title')
            resource_id = request.POST.get('resource')
            description = request.POST.get('description', '')
            start_time = parse_datetime(request.POST.get('start_time'))
            end_time = parse_datetime(request.POST.get('end_time'))

            # Make datetimes timezone-aware if they're not already
            if start_time and timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            if end_time and timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            maintenance_type = request.POST.get('maintenance_type')
            blocks_booking = request.POST.get('blocks_booking') == 'on'
            is_recurring = request.POST.get('is_recurring') == 'on'

            # Validation
            if not all([title, resource_id, start_time, end_time, maintenance_type]):
                return JsonResponse({'success': False, 'error': 'All required fields must be filled'})

            if end_time <= start_time:
                return JsonResponse({'success': False, 'error': 'End time must be after start time'})

            resource = get_object_or_404(Resource, id=resource_id)

            # Handle recurring pattern
            recurring_pattern = None
            if is_recurring and request.POST.get('recurring_pattern'):
                recurring_pattern = json.loads(request.POST.get('recurring_pattern'))

            # Create maintenance
            maintenance = Maintenance.objects.create(
                resource=resource,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                maintenance_type=maintenance_type,
                blocks_booking=blocks_booking,
                is_recurring=is_recurring,
                recurring_pattern=recurring_pattern,
                created_by=request.user
            )

            return JsonResponse({'success': True, 'message': 'Maintenance period scheduled successfully'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_edit_maintenance_view(request, maintenance_id):
    """Edit or view an existing maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)

    if request.method == 'GET':
        # Return maintenance data for viewing/editing
        maintenance_data = {
            'id': maintenance.id,
            'title': maintenance.title,
            'description': maintenance.description,
            'resource_id': maintenance.resource.id,
            'resource_name': maintenance.resource.name,
            'start_time': maintenance.start_time.strftime('%Y-%m-%dT%H:%M'),
            'end_time': maintenance.end_time.strftime('%Y-%m-%dT%H:%M'),
            'maintenance_type': maintenance.maintenance_type,
            'blocks_booking': maintenance.blocks_booking,
            'is_recurring': maintenance.is_recurring,
            'recurring_pattern': maintenance.recurring_pattern,
            'created_by': maintenance.created_by.get_full_name() or maintenance.created_by.username,
            'created_at': maintenance.created_at.strftime('%Y-%m-%d %H:%M'),
        }

        # Generate HTML for view modal
        from django.template.loader import render_to_string
        html = render_to_string('booking/maintenance_detail.html', {'maintenance': maintenance}, request=request)

        return JsonResponse({
            'success': True,
            'maintenance': maintenance_data,
            'html': html
        })

    elif request.method == 'POST':
        # Update maintenance
        try:
            from django.utils.dateparse import parse_datetime

            maintenance.title = request.POST.get('title')
            maintenance.description = request.POST.get('description', '')

            # Parse and make datetimes timezone-aware
            start_time = parse_datetime(request.POST.get('start_time'))
            end_time = parse_datetime(request.POST.get('end_time'))

            if start_time and timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            if end_time and timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            maintenance.start_time = start_time
            maintenance.end_time = end_time
            maintenance.maintenance_type = request.POST.get('maintenance_type')
            maintenance.blocks_booking = request.POST.get('blocks_booking') == 'on'

            # Validation
            if maintenance.end_time <= maintenance.start_time:
                return JsonResponse({'success': False, 'error': 'End time must be after start time'})

            # Update resource if changed
            resource_id = request.POST.get('resource')
            if resource_id and str(maintenance.resource.id) != resource_id:
                maintenance.resource = get_object_or_404(Resource, id=resource_id)

            maintenance.save()

            return JsonResponse({'success': True, 'message': 'Maintenance period updated successfully'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_delete_maintenance_view(request, maintenance_id):
    """Delete a maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)

    if request.method == 'POST':
        try:
            maintenance_title = maintenance.title
            maintenance.delete()
            return JsonResponse({'success': True, 'message': f'Maintenance period "{maintenance_title}" deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def download_booking_invitation(request, booking_id):
    """Download a calendar invitation for a specific booking."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    from booking.models import Booking

    booking = get_object_or_404(Booking, id=booking_id)

    # Check permissions - user must be the booking owner or have admin access
    if not (booking.user == request.user or
            request.user.userprofile.role in ['technician', 'sysadmin'] or
            request.user.groups.filter(name='Lab Admin').exists()):
        messages.error(request, "You don't have permission to download this booking invitation.")
        return redirect('booking:my_bookings')

    # Generate ICS invitation
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_booking_invitation(booking)

    # Create filename
    safe_title = booking.title.replace(' ', '-').replace('/', '-')
    filename = f"booking-{safe_title}-{booking.start_time.strftime('%Y%m%d')}.ics"

    return create_ics_response(ics_content, filename)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def download_maintenance_invitation(request, maintenance_id):
    """Download a calendar invitation for a specific maintenance period."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    from booking.models import Maintenance

    maintenance = get_object_or_404(Maintenance, id=maintenance_id)

    # Generate ICS invitation
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_maintenance_invitation(maintenance)

    # Create filename
    safe_title = maintenance.title.replace(' ', '-').replace('/', '-')
    filename = f"maintenance-{safe_title}-{maintenance.start_time.strftime('%Y%m%d')}.ics"

    return create_ics_response(ics_content, filename)


@login_required


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_inductions_view(request):
    """Manage lab induction status for users."""
    from django.db.models import Q
    from django.core.paginator import Paginator
    from booking.models import UserProfile
    from django.contrib.auth.models import User

    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '').strip()

    # Base queryset - users with profiles
    users = User.objects.select_related('userprofile').filter(userprofile__isnull=False)

    # Apply status filter
    if status_filter == 'inducted':
        users = users.filter(userprofile__is_inducted=True)
    elif status_filter == 'not_inducted':
        users = users.filter(userprofile__is_inducted=False)

    # Apply search filter
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(userprofile__student_id__icontains=search_query)
        )

    # Handle POST requests for updating induction status
    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')

        try:
            user = User.objects.select_related('userprofile').get(id=user_id)
            user_profile = user.userprofile

            if action == 'mark_inducted':
                user_profile.is_inducted = True
                user_profile.save()

                # Also mark safety induction as confirmed on any pending access requests
                from booking.models import AccessRequest
                from django.utils import timezone
                pending_requests = AccessRequest.objects.filter(
                    user=user,
                    status='pending',
                    safety_induction_confirmed=False
                )

                for access_request in pending_requests:
                    access_request.safety_induction_confirmed = True
                    access_request.safety_induction_confirmed_by = request.user
                    access_request.safety_induction_confirmed_at = timezone.now()
                    access_request.safety_induction_notes = f"Confirmed via general lab induction by {request.user.get_full_name() or request.user.username}"
                    access_request.save(update_fields=[
                        'safety_induction_confirmed', 'safety_induction_confirmed_by',
                        'safety_induction_confirmed_at', 'safety_induction_notes', 'updated_at'
                    ])

                messages.success(request, f'Successfully marked {user.get_full_name() or user.username} as inducted.')

                # Send notification to user
                from booking.models import Notification
                Notification.objects.create(
                    user=user,
                    title='Lab Induction Completed',
                    message=f'Your lab induction has been confirmed by {request.user.get_full_name() or request.user.username}. You can now request access to lab resources.',
                    notification_type='induction',
                    is_read=False
                )

            elif action == 'mark_not_inducted':
                user_profile.is_inducted = False
                user_profile.save()

                # Also clear safety induction confirmation on any pending access requests
                from booking.models import AccessRequest
                pending_requests = AccessRequest.objects.filter(
                    user=user,
                    status='pending',
                    safety_induction_confirmed=True
                )

                for access_request in pending_requests:
                    access_request.safety_induction_confirmed = False
                    access_request.safety_induction_confirmed_by = None
                    access_request.safety_induction_confirmed_at = None
                    access_request.safety_induction_notes = ""
                    access_request.save(update_fields=[
                        'safety_induction_confirmed', 'safety_induction_confirmed_by',
                        'safety_induction_confirmed_at', 'safety_induction_notes', 'updated_at'
                    ])

                messages.success(request, f'Successfully marked {user.get_full_name() or user.username} as not inducted.')

        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except Exception as e:
            messages.error(request, f'Error updating induction status: {str(e)}')

        return redirect('booking:lab_admin_inductions')

    # Order by induction status (not inducted first) then by name
    users = users.order_by('userprofile__is_inducted', 'first_name', 'last_name')

    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    # Count statistics
    total_users = User.objects.filter(userprofile__isnull=False).count()
    inducted_count = User.objects.filter(userprofile__is_inducted=True).count()
    not_inducted_count = total_users - inducted_count

    context = {
        'users': users_page,
        'total_users': total_users,
        'inducted_count': inducted_count,
        'not_inducted_count': not_inducted_count,
        'status_filter': status_filter,
        'search_query': search_query,
    }

    return render(request, 'booking/lab_admin_inductions.html', context)


