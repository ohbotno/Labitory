"""
Training-related models for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .resources import Resource


class RiskAssessment(models.Model):
    """Risk assessments for resource access."""
    ASSESSMENT_TYPES = [
        ('general', 'General Risk Assessment'),
        ('chemical', 'Chemical Hazard Assessment'),
        ('biological', 'Biological Safety Assessment'),
        ('radiation', 'Radiation Safety Assessment'),
        ('mechanical', 'Mechanical Safety Assessment'),
        ('electrical', 'Electrical Safety Assessment'),
        ('fire', 'Fire Safety Assessment'),
        ('environmental', 'Environmental Impact Assessment'),
    ]
    
    RISK_LEVELS = [
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk'),
        ('critical', 'Critical Risk'),
    ]
    
    title = models.CharField(max_length=200)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='risk_assessments')
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPES, default='general')
    description = models.TextField(help_text="Detailed description of the assessment")
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS, default='medium')
    
    # Assessment content
    hazards_identified = models.JSONField(default=list, help_text="List of identified hazards")
    control_measures = models.JSONField(default=list, help_text="Control measures and mitigation steps")
    emergency_procedures = models.TextField(blank=True, help_text="Emergency response procedures")
    ppe_requirements = models.JSONField(default=list, help_text="Personal protective equipment requirements")
    
    # Assessment lifecycle
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assessments')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_assessments')
    approved_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateField(help_text="Assessment expiry date")
    review_frequency_months = models.PositiveIntegerField(default=12, help_text="Review frequency in months")
    
    # Status tracking
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=True, help_text="Must be completed before access")
    requires_renewal = models.BooleanField(default=True, help_text="Requires periodic renewal")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_riskassessment'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.resource.name}"
    
    @property
    def is_expired(self):
        """Check if the assessment has expired."""
        return timezone.now().date() > self.valid_until
    
    @property
    def is_due_for_review(self):
        """Check if assessment is due for review."""
        if not self.approved_at:
            return True
        review_due = self.approved_at + timedelta(days=self.review_frequency_months * 30)
        return timezone.now() > review_due


class UserRiskAssessment(models.Model):
    """Tracks user completion of risk assessments."""
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted for Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='risk_assessments')
    risk_assessment = models.ForeignKey(RiskAssessment, on_delete=models.CASCADE, related_name='user_completions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    
    # Completion tracking
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Assessment responses
    responses = models.JSONField(default=dict, help_text="User responses to assessment questions")
    assessor_notes = models.TextField(blank=True, help_text="Notes from the person reviewing the assessment")
    user_declaration = models.TextField(blank=True, help_text="User declaration and acknowledgment")
    
    # File upload
    assessment_file = models.FileField(
        upload_to='risk_assessments/%Y/%m/',
        blank=True,
        null=True,
        validators=[],  # Will be populated with file validators
        help_text="Supporting documents (Excel, PDF, Word, etc.) - Max 20MB"
    )
    
    # Review information
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_assessments')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    # Score and outcome
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pass_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=80.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_userriskassessment'
        unique_together = ['user', 'risk_assessment', 'status']  # Prevent duplicate active assessments
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.risk_assessment.title} ({self.get_status_display()})"
    
    @property
    def is_expired(self):
        """Check if the user's assessment completion has expired."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if the assessment completion is currently valid."""
        return self.status == 'approved' and not self.is_expired
    
    def start_assessment(self):
        """Start the assessment process."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def submit_for_review(self, responses, declaration=""):
        """Submit assessment for review."""
        self.status = 'submitted'
        self.submitted_at = timezone.now()
        self.responses = responses
        self.user_declaration = declaration
        self.save(update_fields=['status', 'submitted_at', 'responses', 'user_declaration', 'updated_at'])
    
    def approve(self, reviewed_by, score=None, notes=""):
        """Approve the assessment."""
        self.status = 'approved'
        self.completed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        
        if score is not None:
            self.score_percentage = score
        
        # Set expiry based on risk assessment renewal requirements
        if self.risk_assessment.requires_renewal:
            self.expires_at = timezone.now() + timedelta(days=self.risk_assessment.review_frequency_months * 30)
        
        self.save()
    
    def reject(self, reviewed_by, notes=""):
        """Reject the assessment."""
        self.status = 'rejected'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()


class TrainingCourse(models.Model):
    """Training courses required for resource access."""
    COURSE_TYPES = [
        ('induction', 'General Induction'),
        ('safety', 'Safety Training'),
        ('equipment', 'Equipment Specific Training'),
        ('software', 'Software Training'),
        ('advanced', 'Advanced Certification'),
        ('refresher', 'Refresher Course'),
    ]
    
    DELIVERY_METHODS = [
        ('in_person', 'In-Person Training'),
        ('online', 'Online Training'),
        ('hybrid', 'Hybrid Training'),
        ('self_study', 'Self-Study'),
        ('assessment_only', 'Assessment Only'),
    ]
    
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, help_text="Unique course code")
    description = models.TextField()
    course_type = models.CharField(max_length=20, choices=COURSE_TYPES, default='equipment')
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS, default='in_person')
    
    # Course requirements
    prerequisite_courses = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='dependent_courses')
    duration_hours = models.DecimalField(max_digits=5, decimal_places=1, help_text="Course duration in hours")
    max_participants = models.PositiveIntegerField(default=10, help_text="Maximum participants per session")
    
    # Content and materials
    learning_objectives = models.JSONField(default=list, help_text="List of learning objectives")
    course_materials = models.JSONField(default=list, help_text="Required materials and resources")
    assessment_criteria = models.JSONField(default=list, help_text="Assessment criteria and methods")
    
    # Validity and renewal
    valid_for_months = models.PositiveIntegerField(default=24, help_text="Certificate validity in months")
    requires_practical_assessment = models.BooleanField(default=False)
    pass_mark_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=80.00)
    
    # Management
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_courses')
    instructors = models.ManyToManyField(User, related_name='instructor_courses', blank=True)
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=False, help_text="Required for all users")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_trainingcourse'
        ordering = ['title']
    
    def __str__(self):
        return f"{self.code} - {self.title}"
    
    def get_available_instructors(self):
        """Get list of users who can instruct this course."""
        return self.instructors.filter(is_active=True)



class UserTraining(models.Model):
    """Tracks user completion of training courses."""
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='training_records')
    training_course = models.ForeignKey(TrainingCourse, on_delete=models.CASCADE, related_name='user_completions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    
    # Enrollment and completion
    enrolled_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Training session details
    instructor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='taught_training')
    session_date = models.DateTimeField(null=True, blank=True)
    session_location = models.CharField(max_length=200, blank=True)
    
    # Assessment results
    theory_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    practical_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField(default=False)
    
    # Feedback and notes
    instructor_notes = models.TextField(blank=True)
    user_feedback = models.TextField(blank=True)
    
    # Certificate details
    certificate_number = models.CharField(max_length=100, blank=True, unique=True)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_usertraining'
        unique_together = ['user', 'training_course', 'status']  # Prevent duplicate active records
        ordering = ['-completed_at', '-enrolled_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.training_course.title} ({self.get_status_display()})"
    
    @property
    def is_expired(self):
        """Check if the training has expired."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if the training completion is currently valid."""
        return self.status == 'completed' and self.passed and not self.is_expired
    
    def start_training(self):
        """Start the training."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def complete_training(self, theory_score=None, practical_score=None, instructor=None, notes="", send_notification=True):
        """Complete the training with scores."""
        self.theory_score = theory_score
        self.practical_score = practical_score
        self.instructor = instructor
        self.instructor_notes = notes
        
        # Calculate overall score
        if theory_score is not None and practical_score is not None:
            self.overall_score = (theory_score + practical_score) / 2
        elif theory_score is not None:
            self.overall_score = theory_score
        elif practical_score is not None:
            self.overall_score = practical_score
        
        # Check if passed
        if self.overall_score is not None:
            self.passed = self.overall_score >= self.training_course.pass_mark_percentage
        
        if self.passed:
            self.status = 'completed'
            self.completed_at = timezone.now()
            
            # Set expiry date
            if self.training_course.valid_for_months:
                self.expires_at = timezone.now() + timedelta(days=self.training_course.valid_for_months * 30)
            
            # Generate certificate number
            if not self.certificate_number:
                self.certificate_number = f"{self.training_course.code}-{self.user.id}-{timezone.now().strftime('%Y%m%d')}"
                self.certificate_issued_at = timezone.now()
        else:
            self.status = 'failed'

        self.save()

        # Send notifications
        if send_notification:
            # Training notifications removed during system simplification
            # TODO: Re-implement with simplified notification system if needed
            pass

    def reset_for_retry(self):
        """Reset training status to allow for retry after failure or cancellation."""
        if self.status not in ['failed', 'cancelled', 'expired']:
            raise ValueError("Can only reset failed, cancelled, or expired training")

        # Reset status and scores
        self.status = 'enrolled'
        self.theory_score = None
        self.practical_score = None
        self.overall_score = None
        self.passed = False
        self.completed_at = None
        self.certificate_number = ""
        self.certificate_issued_at = None
        self.instructor_notes = ""
        self.user_feedback = ""

        # Keep session date if it was scheduled
        # Reset enrolled date to now
        self.enrolled_at = timezone.now()

        self.save(update_fields=[
            'status', 'theory_score', 'practical_score', 'overall_score',
            'passed', 'completed_at', 'certificate_number', 'certificate_issued_at',
            'instructor_notes', 'user_feedback', 'enrolled_at', 'updated_at'
        ])

    def mark_as_completed_by_admin(self, instructor=None, notes=""):
        """Mark training as completed by admin confirmation without requiring scores."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.passed = True  # Admin confirmation means they passed
        self.instructor = instructor
        self.instructor_notes = notes

        # Set expiry date
        if self.training_course.valid_for_months:
            self.expires_at = timezone.now() + timedelta(days=self.training_course.valid_for_months * 30)

        # Generate certificate number
        if not self.certificate_number:
            self.certificate_number = f"{self.training_course.code}-{self.user.id}-{timezone.now().strftime('%Y%m%d')}"
            self.certificate_issued_at = timezone.now()

        self.save()

        # Update related access requests
        self._update_access_requests_on_completion(instructor)

        # Send completion notification
        # Training notifications removed during system simplification
        # TODO: Re-implement with simplified notification system if needed
        pass

    def _update_access_requests_on_completion(self, instructor=None):
        """Update related access requests when training is completed."""
        from booking.models import AccessRequest, ResourceTrainingRequirement

        training_course = self.training_course

        # Get resources that require this training
        required_resources = ResourceTrainingRequirement.objects.filter(
            training_course=training_course,
            is_mandatory=True
        ).values_list('resource_id', flat=True)

        # Find pending access requests for these resources
        pending_requests = AccessRequest.objects.filter(
            user=self.user,
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
                # Check if user has completed this training
                if not UserTraining.objects.filter(
                    user=self.user,
                    training_course=req.training_course,
                    status='completed'
                ).exists():
                    all_training_met = False
                    break

            # If all training is met, confirm lab training
            if all_training_met:
                request.confirm_lab_training(
                    confirmed_by=instructor or self.user,
                    notes=f'Auto-confirmed: All required training completed including {training_course.title}'
                )