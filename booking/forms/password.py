# booking/forms/password.py
"""
Password-related forms with enhanced security features.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone
from ..utils.password_utils import get_password_strength_score, generate_password_requirements_html


class StrongPasswordChangeForm(PasswordChangeForm):
    """Enhanced password change form with strength checking."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Update field attributes for better UX
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your current password',
            'autocomplete': 'current-password'
        })
        
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your new password',
            'autocomplete': 'new-password',
            'data-password-strength': 'true'
        })
        
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm your new password',
            'autocomplete': 'new-password'
        })
        
        # Add help text with requirements
        self.fields['new_password1'].help_text = generate_password_requirements_html()

    def clean_new_password1(self):
        """Validate new password with enhanced checks."""
        password = self.cleaned_data.get('new_password1')
        
        if password:
            # Run Django's built-in password validation
            validate_password(password, self.user)
            
            # Check password strength
            strength = get_password_strength_score(password)
            if strength['score'] < 60:  # Require at least "Strong" password
                raise ValidationError(
                    f"Password strength is {strength['strength']} ({strength['score']}/100). "
                    f"Please choose a stronger password. Issues: {'; '.join(strength['feedback'])}"
                )
        
        return password

    def save(self, commit=True):
        """Save password and update password change timestamp."""
        user = super().save(commit=False)
        
        if commit:
            user.save()
            
            # Update password change timestamp in user profile
            try:
                profile = user.userprofile
                profile.password_changed_at = timezone.now()
                profile.save()
            except:
                pass  # Profile might not exist yet
                
        return user


class StrongSetPasswordForm(SetPasswordForm):
    """Enhanced set password form for password resets."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Update field attributes
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your new password',
            'autocomplete': 'new-password',
            'data-password-strength': 'true'
        })
        
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm your new password',
            'autocomplete': 'new-password'
        })
        
        # Add help text
        self.fields['new_password1'].help_text = generate_password_requirements_html()

    def clean_new_password1(self):
        """Validate new password with enhanced checks."""
        password = self.cleaned_data.get('new_password1')
        
        if password:
            # Run Django's built-in password validation
            validate_password(password, self.user)
            
            # Check password strength
            strength = get_password_strength_score(password)
            if strength['score'] < 60:
                raise ValidationError(
                    f"Password strength is {strength['strength']} ({strength['score']}/100). "
                    f"Please choose a stronger password. Issues: {'; '.join(strength['feedback'])}"
                )
        
        return password

    def save(self, commit=True):
        """Save password and update password change timestamp."""
        user = super().save(commit=False)
        
        if commit:
            user.save()
            
            # Update password change timestamp
            try:
                profile = user.userprofile
                profile.password_changed_at = timezone.now()
                profile.save()
            except:
                pass
                
        return user


class PasswordStrengthWidget(forms.PasswordInput):
    """Password input widget with strength meter."""
    
    template_name = 'booking/widgets/password_strength.html'
    
    def __init__(self, *args, **kwargs):
        self.show_strength_meter = kwargs.pop('show_strength_meter', True)
        super().__init__(*args, **kwargs)
        
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['show_strength_meter'] = self.show_strength_meter
        return context


class EnhancedUserCreationForm(forms.ModelForm):
    """Enhanced user creation form with strong password requirements."""
    
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=PasswordStrengthWidget(),
        help_text=generate_password_requirements_html(),
    )
    password2 = forms.CharField(
        label='Password confirmation',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        strip=False,
        help_text='Enter the same password as before, for verification.',
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Update password1 widget attributes
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'data-password-strength': 'true',
            'autocomplete': 'new-password'
        })

    def clean_password1(self):
        """Validate password1 with enhanced checks."""
        password = self.cleaned_data.get('password1')
        
        if password:
            # Create temporary user for validation context
            temp_user = User(
                username=self.cleaned_data.get('username', ''),
                email=self.cleaned_data.get('email', ''),
                first_name=self.cleaned_data.get('first_name', ''),
                last_name=self.cleaned_data.get('last_name', ''),
            )
            
            # Run Django's built-in password validation
            validate_password(password, temp_user)
            
            # Check password strength
            strength = get_password_strength_score(password)
            if strength['score'] < 60:
                raise ValidationError(
                    f"Password strength is {strength['strength']} ({strength['score']}/100). "
                    f"Please choose a stronger password. Issues: {'; '.join(strength['feedback'])}"
                )
        
        return password

    def clean_password2(self):
        """Check that the two password entries match."""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        
        return password2

    def save(self, commit=True):
        """Save user with hashed password and set password change timestamp."""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()
            
            # Set initial password change timestamp
            try:
                profile = user.userprofile
                profile.password_changed_at = timezone.now()
                profile.save()
            except:
                pass
                
        return user