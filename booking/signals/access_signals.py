"""
Signals for automatic access request updates when prerequisites are completed.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from booking.models import UserProfile, UserTraining, UserRiskAssessment, AccessRequest


@receiver(post_save, sender=UserProfile)
def update_access_requests_on_induction(sender, instance, **kwargs):
    """Update access requests when user completes induction."""
    if instance.is_inducted:
        # Update all pending access requests for this user
        pending_requests = AccessRequest.objects.filter(
            user=instance.user,
            status='pending',
            safety_induction_confirmed=False
        )

        for request in pending_requests:
            request.confirm_safety_induction(
                confirmed_by=instance.user,  # Auto-confirmation
                notes='Auto-confirmed: User profile updated to show induction completed'
            )


@receiver(post_save, sender=UserTraining)
def update_access_requests_on_training_completion(sender, instance, **kwargs):
    """Update access requests when user completes training."""
    if instance.status == 'completed' and instance.is_valid:
        # Find access requests that need this training
        training_course = instance.training_course

        # Get resources that require this training
        from booking.models import ResourceTrainingRequirement

        required_resources = ResourceTrainingRequirement.objects.filter(
            training_course=training_course,
            is_mandatory=True
        ).values_list('resource_id', flat=True)

        # Update pending access requests for these resources
        pending_requests = AccessRequest.objects.filter(
            user=instance.user,
            resource_id__in=required_resources,
            status='pending',
            lab_training_confirmed=False
        )

        for request in pending_requests:
            # Check if all training requirements for this resource are now met
            all_training_met = True
            resource_training_reqs = ResourceTrainingRequirement.objects.filter(
                resource=request.resource,
                is_mandatory=True
            )

            for req in resource_training_reqs:
                if not req.required_for_access_types or request.access_type in req.required_for_access_types:
                    # Check if user has completed this training
                    has_training = UserTraining.objects.filter(
                        user=instance.user,
                        training_course=req.training_course,
                        status='completed'
                    ).exists()

                    if not has_training:
                        all_training_met = False
                        break

            # If all training is met, confirm lab training
            if all_training_met:
                request.confirm_lab_training(
                    confirmed_by=instance.user,  # Auto-confirmation
                    notes=f'Auto-confirmed: All required training completed including {training_course.title}'
                )


@receiver(post_save, sender=UserRiskAssessment)
def update_access_requests_on_risk_assessment_approval(sender, instance, **kwargs):
    """Update access requests when user's risk assessment is approved."""
    if instance.status == 'approved':
        # Find access requests that need this risk assessment
        resource = instance.risk_assessment.resource

        # Update pending access requests for this resource
        pending_requests = AccessRequest.objects.filter(
            user=instance.user,
            resource=resource,
            status='pending',
            risk_assessment_confirmed=False
        )

        for request in pending_requests:
            # Check if all risk assessments for this resource are now met
            all_assessments_met = True

            if request.resource.requires_risk_assessment:
                from booking.models import RiskAssessment

                required_assessments = RiskAssessment.objects.filter(
                    resource=request.resource,
                    is_mandatory=True,
                    is_active=True
                )

                for assessment in required_assessments:
                    has_assessment = UserRiskAssessment.objects.filter(
                        user=instance.user,
                        risk_assessment=assessment,
                        status='approved'
                    ).exists()

                    if not has_assessment:
                        all_assessments_met = False
                        break

                # If all assessments are met, confirm risk assessment
                if all_assessments_met:
                    request.confirm_risk_assessment(
                        confirmed_by=instance.user,  # Auto-confirmation
                        notes=f'Auto-confirmed: All required risk assessments approved including {instance.risk_assessment.title}'
                    )