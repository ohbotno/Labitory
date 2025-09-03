# booking/views/modules/auth.py
"""
Authentication-related views for the Aperture Booking system.

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
from django.contrib.auth.views import PasswordResetView, LoginView
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone

from ...forms import UserRegistrationForm, CustomPasswordResetForm, CustomSetPasswordForm
from ...models import EmailVerificationToken, PasswordResetToken, UserProfile


def register_view(request):
    """User registration view."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Get the verification token for development mode
            from django.conf import settings
            token = EmailVerificationToken.objects.filter(user=user, is_used=False).first()
            
            if settings.DEBUG and token:
                # In development mode, show the verification URL
                verification_url = request.build_absolute_uri(f'/verify-email/{token.token}/')
                messages.success(
                    request, 
                    f'<strong>Registration Successful!</strong><br><br>'
                    f'<i class="bi bi-info-circle"></i> <strong>Important:</strong> Your account has been created but is currently <strong>inactive</strong>.<br><br>'
                    f'<i class="bi bi-envelope"></i> <strong>Next Steps:</strong><br>'
                    f'1. Check your email ({user.email}) for a verification link<br>'
                    f'2. Click the verification link to activate your account<br>'
                    f'3. Return here to log in<br><br>'
                    f'<i class="bi bi-gear"></i> <strong>Development Mode:</strong> You can verify directly using this link: <a href="{verification_url}" target="_blank" class="btn btn-sm btn-outline-primary">Verify Account Now</a><br><br>'
                    f'<small class="text-muted"><i class="bi bi-clock"></i> You cannot log in until your email is verified.</small>'
                )
            else:
                messages.success(
                    request, 
                    f'<strong>Registration Successful!</strong><br><br>'
                    f'<i class="bi bi-info-circle"></i> <strong>Important:</strong> Your account has been created but is currently <strong>inactive</strong>.<br><br>'
                    f'<i class="bi bi-envelope"></i> <strong>Next Steps:</strong><br>'
                    f'1. Check your email ({user.email}) for a verification link<br>'
                    f'2. Click the verification link to activate your account<br>'
                    f'3. Return here to log in<br><br>'
                    f'<small class="text-muted"><i class="bi bi-clock"></i> You cannot log in until your email is verified. If you don\'t see the email, check your spam folder or <a href="/resend-verification/">request a new verification email</a>.</small>'
                )
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
        # Clear any existing messages when showing the registration form
        list(messages.get_messages(request))
    
    return render(request, 'registration/register.html', {'form': form})


def verify_email_view(request, token):
    """Email verification view."""
    verification_token = get_object_or_404(EmailVerificationToken, token=token)
    
    if verification_token.is_used:
        messages.warning(request, 'This verification link has already been used.')
        return redirect('login')
    
    if verification_token.is_expired():
        messages.error(request, 'This verification link has expired. Please contact support.')
        return redirect('login')
    
    # Activate user and mark email as verified
    user = verification_token.user
    user.is_active = True
    user.save()
    
    profile = user.userprofile
    profile.email_verified = True
    profile.save()
    
    verification_token.is_used = True
    verification_token.save()
    
    messages.success(request, 'Email verified successfully! You can now log in.')
    return redirect('login')


def resend_verification_view(request):
    """Resend verification email view."""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email, is_active=False)
            
            # Check if there's an existing unused token
            try:
                token = EmailVerificationToken.objects.get(user=user, is_used=False)
                if token.is_expired():
                    token.delete()
                    token = EmailVerificationToken.objects.create(user=user)
            except EmailVerificationToken.DoesNotExist:
                token = EmailVerificationToken.objects.create(user=user)
            
            # Send verification email
            form = UserRegistrationForm()
            form.send_verification_email(user, token)
            
            messages.success(request, 'Verification email has been resent. Please check your inbox.')
            
        except User.DoesNotExist:
            messages.error(request, 'No unverified account found with this email address.')
    
    return render(request, 'registration/resend_verification.html')


class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view using our token system."""
    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    success_url = '/password-reset-done/'
    
    def form_valid(self, form):
        form.save(request=self.request)
        return redirect(self.success_url)


def password_reset_confirm_view(request, token):
    """Custom password reset confirmation view."""
    reset_token = get_object_or_404(PasswordResetToken, token=token)
    
    if reset_token.is_used:
        messages.error(request, 'This password reset link has already been used.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if reset_token.is_expired():
        messages.error(request, 'This password reset link has expired.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if request.method == 'POST':
        form = CustomSetPasswordForm(reset_token.user, request.POST)
        if form.is_valid():
            form.save()
            reset_token.is_used = True
            reset_token.save()
            messages.success(request, 'Your password has been set successfully.')
            return redirect('password_reset_complete')
    else:
        form = CustomSetPasswordForm(reset_token.user)
    
    return render(request, 'registration/password_reset_confirm.html', {
        'form': form,
        'validlink': True,
    })


def password_reset_done_view(request):
    """Password reset done view."""
    return render(request, 'registration/password_reset_done.html')


def password_reset_complete_view(request):
    """Password reset complete view."""
    return render(request, 'registration/password_reset_complete.html')


class CustomLoginView(LoginView):
    """Custom login view that handles first login redirect logic."""
    
    def get_success_url(self):
        """Redirect to about page on first login, dashboard on subsequent logins."""
        user = self.request.user
        
        try:
            profile = user.userprofile
            
            # Check if this is the user's first login
            if profile.first_login is None:
                # Mark the first login time
                profile.first_login = timezone.now()
                profile.save()
                
                # Redirect to about page for first-time users
                return '/about/'
            else:
                # Redirect to dashboard for returning users
                return '/dashboard/'
                
        except UserProfile.DoesNotExist:
            # If no profile exists, redirect to about page
            return '/about/'