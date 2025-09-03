"""
Tutorial and onboarding models for the Labitory.

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


class TutorialCategory(models.Model):
    """Categories for organizing tutorials."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fas fa-graduation-cap')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_tutorialcategory'
        ordering = ['order', 'name']
        verbose_name = 'Tutorial Category'
        verbose_name_plural = 'Tutorial Categories'
    
    def __str__(self):
        return self.name


class Tutorial(models.Model):
    """Individual tutorial configurations."""
    TRIGGER_TYPES = [
        ('manual', 'Manual Start'),
        ('first_login', 'First Login'),
        ('role_change', 'Role Change'),
        ('page_visit', 'Page Visit'),
        ('feature_access', 'Feature Access'),
    ]
    
    DIFFICULTY_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(TutorialCategory, on_delete=models.CASCADE, related_name='tutorials')
    
    # Targeting
    target_roles = models.JSONField(default=list, help_text="User roles this tutorial applies to")
    target_pages = models.JSONField(default=list, help_text="Pages where this tutorial can be triggered")
    
    # Configuration
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPES, default='manual')
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='beginner')
    estimated_duration = models.PositiveIntegerField(help_text="Estimated duration in minutes")
    
    # Content
    steps = models.JSONField(default=list, help_text="Tutorial steps configuration")
    
    # Settings
    is_mandatory = models.BooleanField(default=False, help_text="Whether users must complete this tutorial")
    is_active = models.BooleanField(default=True)
    auto_start = models.BooleanField(default=False, help_text="Auto-start when conditions are met")
    allow_skip = models.BooleanField(default=True, help_text="Allow users to skip this tutorial")
    show_progress = models.BooleanField(default=True, help_text="Show progress indicator")
    
    # Metadata
    version = models.CharField(max_length=10, default='1.0')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tutorials')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_tutorial'
        ordering = ['category__order', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category.name})"
    
    def is_applicable_for_user(self, user):
        """Check if tutorial applies to a specific user."""
        if not self.is_active:
            return False
        
        if not user.is_authenticated:
            return False
        
        try:
            user_role = user.userprofile.role
        except:
            user_role = 'student'  # Default role
        
        # Check role targeting
        if self.target_roles and user_role not in self.target_roles:
            return False
        
        return True
    
    def get_next_step(self, current_step):
        """Get the next step in the tutorial."""
        if current_step < len(self.steps) - 1:
            return current_step + 1
        return None
    
    def get_step_count(self):
        """Get total number of steps."""
        return len(self.steps)


class UserTutorialProgress(models.Model):
    """Track user progress through tutorials."""
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tutorial_progress')
    tutorial = models.ForeignKey(Tutorial, on_delete=models.CASCADE, related_name='user_progress')
    
    # Progress tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    current_step = models.PositiveIntegerField(default=0)
    completed_steps = models.JSONField(default=list, help_text="List of completed step indices")
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(auto_now=True)
    
    # Metrics
    time_spent = models.PositiveIntegerField(default=0, help_text="Time spent in seconds")
    attempts = models.PositiveIntegerField(default=0, help_text="Number of times tutorial was started")
    
    # Feedback
    rating = models.PositiveIntegerField(null=True, blank=True, help_text="User rating 1-5")
    feedback = models.TextField(blank=True, help_text="User feedback")
    
    class Meta:
        db_table = 'booking_usertutorialprogress'
        unique_together = ['user', 'tutorial']
        ordering = ['-last_accessed_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.tutorial.name} ({self.status})"
    
    def start_tutorial(self):
        """Start the tutorial."""
        if self.status == 'not_started':
            self.attempts += 1
        
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.current_step = 0
        self.save(update_fields=['status', 'started_at', 'current_step', 'attempts', 'last_accessed_at'])
    
    def complete_step(self, step_index):
        """Mark a step as completed."""
        if step_index not in self.completed_steps:
            self.completed_steps.append(step_index)
            self.completed_steps.sort()
        
        self.current_step = step_index + 1
        self.save(update_fields=['completed_steps', 'current_step', 'last_accessed_at'])
        
        # Check if tutorial is complete
        if len(self.completed_steps) >= self.tutorial.get_step_count():
            self.complete_tutorial()
    
    def complete_tutorial(self):
        """Mark tutorial as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'last_accessed_at'])
    
    def skip_tutorial(self):
        """Mark tutorial as skipped."""
        self.status = 'skipped'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'last_accessed_at'])
    
    @property
    def progress_percentage(self):
        """Calculate completion percentage."""
        total_steps = self.tutorial.get_step_count()
        if total_steps == 0:
            return 100
        return (len(self.completed_steps) / total_steps) * 100
    
    @property
    def is_completed(self):
        """Check if tutorial is completed."""
        return self.status == 'completed'
    
    @property
    def is_in_progress(self):
        """Check if tutorial is in progress."""
        return self.status == 'in_progress'


class TutorialAnalytics(models.Model):
    """Analytics and metrics for tutorials."""
    tutorial = models.OneToOneField(Tutorial, on_delete=models.CASCADE, related_name='analytics')
    
    # Completion metrics
    total_starts = models.PositiveIntegerField(default=0)
    total_completions = models.PositiveIntegerField(default=0)
    total_skips = models.PositiveIntegerField(default=0)
    total_abandons = models.PositiveIntegerField(default=0)
    
    # Time metrics
    average_completion_time = models.PositiveIntegerField(default=0, help_text="Average completion time in seconds")
    average_rating = models.FloatField(default=0.0, help_text="Average user rating")
    
    # Step analytics
    step_completion_rates = models.JSONField(default=dict, help_text="Completion rate for each step")
    step_drop_off_points = models.JSONField(default=list, help_text="Steps where users commonly drop off")
    
    # Updated timestamp
    last_calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_tutorialanalytics'
    
    def __str__(self):
        return f"Analytics for {self.tutorial.name}"
    
    @property
    def completion_rate(self):
        """Calculate completion rate percentage."""
        if self.total_starts == 0:
            return 0
        return (self.total_completions / self.total_starts) * 100
    
    @property
    def skip_rate(self):
        """Calculate skip rate percentage."""
        if self.total_starts == 0:
            return 0
        return (self.total_skips / self.total_starts) * 100
    
    def update_metrics(self):
        """Recalculate all metrics from user progress data."""
        progress_qs = self.tutorial.user_progress.all()
        
        self.total_starts = progress_qs.exclude(status='not_started').count()
        self.total_completions = progress_qs.filter(status='completed').count()
        self.total_skips = progress_qs.filter(status='skipped').count()
        self.total_abandons = progress_qs.filter(status='abandoned').count()
        
        # Calculate average completion time
        completed_progress = progress_qs.filter(status='completed', time_spent__gt=0)
        if completed_progress.exists():
            self.average_completion_time = completed_progress.aggregate(
                models.Avg('time_spent')
            )['time_spent__avg'] or 0
        
        # Calculate average rating
        rated_progress = progress_qs.filter(rating__isnull=False)
        if rated_progress.exists():
            self.average_rating = rated_progress.aggregate(
                models.Avg('rating')
            )['rating__avg'] or 0.0
        
        self.save()