"""
Two-Factor Authentication views for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import pyotp
import qrcode
import io
import base64
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone

from booking.models import TwoFactorAuthentication, TwoFactorSession
from booking.forms.auth import (
    TwoFactorSetupForm,
    TwoFactorVerificationForm,
    TwoFactorDisableForm,
    BackupCodesForm
)


@login_required
def two_factor_setup(request):
    """Setup 2FA for the user."""
    user = request.user
    
    # Check if 2FA is already enabled
    try:
        two_factor = user.two_factor_auth
        if two_factor.is_enabled:
            messages.info(request, "Two-factor authentication is already enabled.")
            return redirect('two_factor_status')
    except TwoFactorAuthentication.DoesNotExist:
        two_factor = None
    
    if request.method == 'POST':
        # Get or create 2FA record
        if not two_factor:
            two_factor, created = TwoFactorAuthentication.objects.get_or_create(user=user)
        
        # Use existing secret or generate new one
        if not two_factor.secret_key:
            two_factor.secret_key = pyotp.random_base32()
            two_factor.save()
        
        form = TwoFactorSetupForm(request.POST, user=user, secret_key=two_factor.secret_key)
        
        if form.is_valid():
            # Enable 2FA
            two_factor.is_enabled = True
            two_factor.updated_at = timezone.now()
            
            # Generate backup codes
            backup_codes = two_factor.generate_backup_codes()
            
            # Save the changes
            two_factor.save()
            
            messages.success(request, "Two-factor authentication has been enabled successfully!")
            
            # Show backup codes
            return render(request, 'booking/two_factor/backup_codes.html', {
                'backup_codes': backup_codes,
                'first_time': True
            })
    else:
        # Generate new secret key for setup
        secret_key = pyotp.random_base32()
        
        # Create or update 2FA record with new secret
        if not two_factor:
            two_factor, created = TwoFactorAuthentication.objects.get_or_create(user=user)
        two_factor.secret_key = secret_key
        two_factor.save()
        
        form = TwoFactorSetupForm(user=user, secret_key=secret_key)
        
        # Generate QR code
        totp_uri = pyotp.totp.TOTP(secret_key).provisioning_uri(
            name=user.email,
            issuer_name='Labitory'
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf)
        qr_code = base64.b64encode(buf.getvalue()).decode()
    
    return render(request, 'booking/two_factor/setup.html', {
        'form': form,
        'qr_code': qr_code if request.method == 'GET' else None,
        'secret_key': secret_key if request.method == 'GET' else None,
    })


@login_required
def two_factor_status(request):
    """View 2FA status and options."""
    try:
        two_factor = request.user.two_factor_auth
    except TwoFactorAuthentication.DoesNotExist:
        two_factor = None
    
    return render(request, 'booking/two_factor/status.html', {
        'two_factor': two_factor,
        'has_backup_codes': two_factor and len(two_factor.backup_codes) > 0
    })


@login_required
@require_http_methods(["GET", "POST"])
def two_factor_disable(request):
    """Disable 2FA for the user."""
    try:
        two_factor = request.user.two_factor_auth
        if not two_factor.is_enabled:
            messages.info(request, "Two-factor authentication is not enabled.")
            return redirect('two_factor_status')
    except TwoFactorAuthentication.DoesNotExist:
        messages.info(request, "Two-factor authentication is not configured.")
        return redirect('two_factor_status')
    
    if request.method == 'POST':
        form = TwoFactorDisableForm(request.POST, user=request.user)
        if form.is_valid():
            # Disable 2FA
            two_factor.is_enabled = False
            two_factor.secret_key = ''
            two_factor.backup_codes = []
            two_factor.save()
            
            # Clear any 2FA sessions
            TwoFactorSession.objects.filter(user=request.user).delete()
            
            messages.success(request, "Two-factor authentication has been disabled.")
            return redirect('two_factor_status')
    else:
        form = TwoFactorDisableForm(user=request.user)
    
    return render(request, 'booking/two_factor/disable.html', {
        'form': form
    })


@login_required
@require_http_methods(["GET", "POST"])
def regenerate_backup_codes(request):
    """Regenerate backup codes."""
    try:
        two_factor = request.user.two_factor_auth
        if not two_factor.is_enabled:
            messages.error(request, "Two-factor authentication is not enabled.")
            return redirect('two_factor_status')
    except TwoFactorAuthentication.DoesNotExist:
        messages.error(request, "Two-factor authentication is not configured.")
        return redirect('two_factor_status')
    
    if request.method == 'POST':
        form = BackupCodesForm(request.POST, user=request.user)
        if form.is_valid():
            # Generate new backup codes
            backup_codes = two_factor.generate_backup_codes()
            
            messages.success(request, "New backup codes have been generated.")
            
            return render(request, 'booking/two_factor/backup_codes.html', {
                'backup_codes': backup_codes,
                'first_time': False
            })
    else:
        form = BackupCodesForm(user=request.user)
    
    return render(request, 'booking/two_factor/regenerate_codes.html', {
        'form': form,
        'remaining_codes': len(two_factor.backup_codes)
    })


def two_factor_verification(request):
    """Verify 2FA code during login."""
    # Check if user is in temporary 2FA session
    if 'pending_2fa_user' not in request.session:
        messages.error(request, "Invalid session. Please login again.")
        return redirect('login')
    
    user_id = request.session.get('pending_2fa_user')
    
    try:
        from django.contrib.auth.models import User
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, "Invalid session. Please login again.")
        return redirect('login')
    
    if request.method == 'POST':
        form = TwoFactorVerificationForm(request.POST, user=user)
        if form.is_valid():
            # Create 2FA session
            TwoFactorSession.create_session(
                user=user,
                session_key=request.session.session_key,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Complete login
            from django.contrib.auth import login
            login(request, user)
            
            # Clean up session
            del request.session['pending_2fa_user']
            
            # Redirect to next URL or dashboard
            next_url = request.session.get('next_url', 'dashboard')
            if 'next_url' in request.session:
                del request.session['next_url']
            
            messages.success(request, f"Welcome back, {user.first_name}!")
            return redirect(next_url)
    else:
        form = TwoFactorVerificationForm(user=user)
    
    return render(request, 'booking/two_factor/verify.html', {
        'form': form,
        'user': user
    })


@login_required
def download_backup_codes(request):
    """Download backup codes as a text file."""
    try:
        two_factor = request.user.two_factor_auth
        if not two_factor.is_enabled or not two_factor.backup_codes:
            messages.error(request, "No backup codes available.")
            return redirect('two_factor_status')
    except TwoFactorAuthentication.DoesNotExist:
        messages.error(request, "Two-factor authentication is not configured.")
        return redirect('two_factor_status')
    
    # Create text content
    content = f"Labitory 2FA Backup Codes\n"
    content += f"User: {request.user.email}\n"
    content += f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n"
    content += "=" * 40 + "\n\n"
    content += "Keep these codes in a safe place.\n"
    content += "Each code can only be used once.\n\n"
    
    for i, code in enumerate(two_factor.backup_codes, 1):
        content += f"{i}. {code}\n"
    
    # Create response
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="labitory_2fa_backup_codes.txt"'
    
    return response