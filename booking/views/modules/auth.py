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
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.conf import settings
from django.db import IntegrityError

from booking.forms import UserRegistrationForm, CustomPasswordResetForm
from booking.forms.password import StrongSetPasswordForm
from ...models import EmailVerificationToken, PasswordResetToken, UserProfile, TwoFactorAuthentication
from ...utils.security_utils import RateLimitMixin
from ...utils.auth_utils import BruteForceProtection, AccountLockout, get_client_ip


@ratelimit(group='registration', key='ip', rate='3/1h', method='POST', block=True)
def register_view(request):
    """User registration view with rate limiting."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
            except IntegrityError as e:
                # Handle the rare case where UserProfile creation fails
                if 'booking_userprofile' in str(e) and 'user_id' in str(e):
                    messages.error(
                        request,
                        '<strong>Registration Error!</strong><br><br>'
                        '<i class="bi bi-exclamation-triangle"></i> <strong>This account already exists!</strong><br><br>'
                        'A user profile for this email address already exists in the system. '
                        'This can happen if:<br>'
                        '• You have already registered with this email<br>'
                        '• An administrator has created an account for you<br><br>'
                        '<strong>What to do:</strong><br>'
                        '• Try logging in with your email and password<br>'
                        '• If you forgot your password, use the password reset option<br>'
                        '• If you need to change your role (e.g., to technician), contact an administrator'
                    )
                    return redirect('login')
                else:
                    # Re-raise other IntegrityErrors
                    raise

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


@ratelimit(group='resend_verification', key='ip', rate='3/1h', method='POST', block=True)
def resend_verification_view(request):
    """Resend verification email view with rate limiting."""
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


class CustomPasswordResetView(RateLimitMixin, PasswordResetView):
    """Custom password reset view using our token system with rate limiting."""
    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    success_url = '/password-reset-done/'
    
    # Rate limiting configuration
    ratelimit_group = 'password_reset'
    ratelimit_rate = f"{getattr(settings, 'RATELIMIT_PASSWORD_RESET', 3)}/1h"
    ratelimit_method = 'POST'
    
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
        form = StrongSetPasswordForm(reset_token.user, request.POST)
        if form.is_valid():
            form.save()
            reset_token.is_used = True
            reset_token.save()
            messages.success(request, 'Your password has been set successfully.')
            return redirect('password_reset_complete')
    else:
        form = StrongSetPasswordForm(reset_token.user)
    
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


class CustomLoginView(RateLimitMixin, LoginView):
    """Custom login view that handles first login redirect logic with rate limiting."""
    
    # Rate limiting configuration
    ratelimit_group = 'login_attempts'
    ratelimit_rate = f"{getattr(settings, 'RATELIMIT_LOGIN_ATTEMPTS', 5)}/15m"
    ratelimit_method = 'POST'
    
    def dispatch(self, request, *args, **kwargs):
        """Check for account lockouts before processing login."""
        if request.method == 'POST' and getattr(settings, 'RATELIMIT_ENABLE', True):
            username = request.POST.get('username', '')
            ip_address = get_client_ip(request)
            
            # Check IP-based lockout
            if BruteForceProtection.is_locked_out(ip_address, 'login'):
                messages.error(request, 'Too many failed login attempts from your IP address. Please try again later.')
                return self.render_to_response(self.get_context_data())
            
            # Check username-based lockout
            if username and BruteForceProtection.is_locked_out(username, 'login'):
                messages.error(request, 'This account has been temporarily locked due to multiple failed login attempts.')
                return self.render_to_response(self.get_context_data())
            
            # Check user account lockout
            if username:
                try:
                    user = User.objects.get(username=username)
                    lockout_info = AccountLockout.is_user_locked(user)
                    if lockout_info:
                        messages.error(request, 'This account has been locked for security reasons. Please contact support.')
                        return self.render_to_response(self.get_context_data())
                except User.DoesNotExist:
                    pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Handle successful login - check for 2FA and clear failed attempts."""
        user = form.get_user()
        ip_address = get_client_ip(self.request)
        
        # Check if user has 2FA enabled
        try:
            two_factor = user.two_factor_auth
            if two_factor.is_enabled:
                # Store user in session for 2FA verification
                self.request.session['pending_2fa_user'] = user.pk
                # Don't call get_success_url() here since user is not logged in yet
                # We'll determine the redirect URL after 2FA verification
                
                # Don't actually log in yet - redirect to 2FA verification
                messages.info(self.request, 'Please enter your 2FA verification code.')
                return redirect('booking:two_factor_verification')
        except TwoFactorAuthentication.DoesNotExist:
            pass  # No 2FA configured, proceed with normal login
        
        # Clear failed attempts on successful login
        BruteForceProtection.clear_failed_attempts(ip_address, 'login')
        BruteForceProtection.clear_failed_attempts(user.username, 'login')
        BruteForceProtection.clear_failed_attempts(user.email, 'login')
        
        # Update last successful login in profile
        if getattr(settings, 'AUTH_TRACK_FAILED_ATTEMPTS', True):
            try:
                profile = user.userprofile
                profile.failed_login_attempts = 0
                profile.last_failed_login = None
                profile.save()
            except:
                pass
        
        return super().form_valid(form)
    
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


# Azure AD SSO Views
import msal
import uuid
from django.http import JsonResponse


def azure_login_view(request):
    """Initiate Azure AD OAuth login flow."""
    try:
        # Check if Azure AD is configured
        if not all([
            getattr(settings, 'AZURE_AD_TENANT_ID', ''),
            getattr(settings, 'AZURE_AD_CLIENT_ID', ''),
            getattr(settings, 'AZURE_AD_CLIENT_SECRET', '')
        ]):
            messages.error(request, 'Azure AD authentication is not configured.')
            return redirect('login')
        
        # Create MSAL app instance
        app = _build_msal_app()
        if not app:
            messages.error(request, 'Failed to initialize Azure AD authentication.')
            return redirect('login')
        
        # Generate state parameter for security
        state = str(uuid.uuid4())
        request.session['auth_state'] = state
        
        # Build authorization URL
        auth_url = app.get_authorization_request_url(
            scopes=getattr(settings, 'AZURE_AD_SCOPES', ['openid', 'profile', 'email']),
            state=state,
            redirect_uri=request.build_absolute_uri('/auth/azure/callback/')
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Azure AD login error: {e}")
        messages.error(request, 'Failed to initiate Azure AD login.')
        return redirect('login')


def azure_callback_view(request):
    """Handle Azure AD OAuth callback."""
    try:
        # Verify state parameter
        if request.GET.get('state') != request.session.get('auth_state'):
            messages.error(request, 'Invalid authentication state.')
            return redirect('login')
        
        # Clear state from session
        if 'auth_state' in request.session:
            del request.session['auth_state']
        
        # Check for error in callback
        if request.GET.get('error'):
            error_desc = request.GET.get('error_description', 'Unknown error')
            messages.error(request, f'Azure AD authentication failed: {error_desc}')
            return redirect('login')
        
        # Get authorization code
        code = request.GET.get('code')
        if not code:
            messages.error(request, 'No authorization code received.')
            return redirect('login')
        
        # Create MSAL app instance
        app = _build_msal_app()
        if not app:
            messages.error(request, 'Failed to process Azure AD authentication.')
            return redirect('login')
        
        # Acquire token using authorization code
        result = app.acquire_token_by_authorization_code(
            code,
            scopes=getattr(settings, 'AZURE_AD_SCOPES', ['openid', 'profile', 'email']),
            redirect_uri=request.build_absolute_uri('/auth/azure/callback/')
        )
        
        if 'error' in result:
            messages.error(request, f'Failed to acquire token: {result.get("error_description")}')
            return redirect('login')
        
        # Authenticate user using custom backend
        from django.contrib.auth import authenticate, login
        user = authenticate(request, azure_token=result)
        
        if user:
            # Check if user has 2FA enabled
            try:
                two_factor = user.two_factor_auth
                if two_factor.is_enabled:
                    # Store user in session for 2FA verification
                    request.session['pending_2fa_user'] = user.pk
                    messages.info(request, 'Please enter your 2FA verification code.')
                    return redirect('booking:two_factor_verification')
            except:
                pass  # No 2FA configured, proceed with normal login
            
            # Complete login
            login(request, user)
            
            # Determine redirect URL using same logic as normal login
            try:
                profile = user.userprofile
                if profile.first_login is None:
                    profile.first_login = timezone.now()
                    profile.save()
                    next_url = '/about/'
                else:
                    next_url = '/dashboard/'
            except:
                next_url = '/about/'
            
            messages.success(request, f'Welcome back, {user.first_name}!')
            return redirect(next_url)
        else:
            messages.error(request, 'Azure AD authentication failed.')
            return redirect('login')
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Azure AD callback error: {e}")
        messages.error(request, 'Authentication failed. Please try again.')
        return redirect('login')


def azure_logout_view(request):
    """Handle Azure AD logout."""
    from django.contrib.auth import logout
    
    # Logout from Django
    logout(request)
    
    # Build Azure AD logout URL
    tenant_id = getattr(settings, 'AZURE_AD_TENANT_ID', '')
    if tenant_id:
        logout_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
        post_logout_redirect = request.build_absolute_uri('/')
        full_logout_url = f"{logout_url}?post_logout_redirect_uri={post_logout_redirect}"
        return redirect(full_logout_url)
    else:
        return redirect('login')


def _build_msal_app():
    """Build MSAL confidential client application."""
    try:
        tenant_id = getattr(settings, 'AZURE_AD_TENANT_ID', '')
        client_id = getattr(settings, 'AZURE_AD_CLIENT_ID', '')
        client_secret = getattr(settings, 'AZURE_AD_CLIENT_SECRET', '')
        
        if not all([tenant_id, client_id, client_secret]):
            return None
        
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        
        return msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )
    except Exception:
        return None