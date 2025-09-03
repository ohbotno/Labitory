# booking/views/licensing.py
"""
Views for license management and activation.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.core.paginator import Paginator
from django.forms import ModelForm
from django import forms

from ..models import LicenseConfiguration, BrandingConfiguration, LicenseValidationLog
from ..services.licensing import license_manager
import json
import logging

logger = logging.getLogger(__name__)


class LicenseActivationForm(forms.Form):
    """Form for license activation."""
    license_key = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your license key',
            'required': True
        }),
        help_text="Enter the license key provided by Labitory"
    )
    
    organization_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your Organization Name',
            'required': True
        }),
        help_text="Name of your organization"
    )
    
    contact_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'contact@yourorg.com',
            'required': True
        }),
        help_text="Primary contact email"
    )
    
    def clean_license_key(self):
        """Validate license key format."""
        license_key = self.cleaned_data.get('license_key', '').strip().upper()
        
        # Basic format validation (expects XXXX-XXXX-XXXX-XXXX format)
        if not license_key:
            raise forms.ValidationError("License key is required")
        
        # Remove any spaces and normalize
        license_key = license_key.replace(' ', '').replace('-', '')
        if len(license_key) < 16:
            raise forms.ValidationError("License key appears to be invalid (too short)")
        
        # Re-format with dashes
        formatted_key = '-'.join([license_key[i:i+4] for i in range(0, len(license_key), 4)])
        
        return formatted_key


class BrandingConfigurationForm(ModelForm):
    """Form for branding configuration."""
    
    class Meta:
        model = BrandingConfiguration
        fields = [
            'app_title', 'company_name', 'logo_primary', 'logo_favicon',
            'color_primary', 'color_secondary', 'color_accent',
            'welcome_message', 'footer_text', 'custom_css',
            'support_email', 'support_phone', 'website_url',
            'email_from_name', 'email_signature',
            'show_powered_by', 'enable_public_registration', 'enable_guest_booking'
        ]
        widgets = {
            'app_title': forms.TextInput(attrs={'class': 'form-control'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'color_primary': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'color_secondary': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'color_accent': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'welcome_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'footer_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'custom_css': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'support_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'support_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'website_url': forms.URLInput(attrs={'class': 'form-control'}),
            'email_from_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email_signature': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


def license_status(request):
    """Display current license status and information."""
    license_info = license_manager.get_license_info()
    enabled_features = license_manager.get_enabled_features()
    
    # Get recent validation logs
    recent_logs = []
    if license_info.get('type') != 'open_source':
        try:
            license_config = license_manager.get_current_license()
            if license_config:
                recent_logs = license_config.validation_logs.all()[:10]
        except Exception:
            pass
    
    context = {
        'license_info': license_info,
        'enabled_features': enabled_features,
        'recent_logs': recent_logs,
        'can_configure': request.user.is_staff,
    }
    
    return render(request, 'licensing/status.html', context)


@staff_member_required
def license_select_open_source(request):
    """Select open source license to remove licensing messages."""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Deactivate any existing licenses
                LicenseConfiguration.objects.filter(is_active=True).update(is_active=False)
                
                # Create open source license configuration
                license_config = LicenseConfiguration.objects.create(
                    license_key='OPEN_SOURCE_GPL3',
                    license_type='open_source',
                    organization_name='Open Source User',
                    organization_slug='open-source',
                    contact_email='user@example.com',
                    is_active=True
                )
                
                # Create default branding configuration for open source
                BrandingConfiguration.objects.create(
                    license=license_config,
                    company_name='Open Source Lab',
                    show_powered_by=False,  # Hide licensing messages for open source
                )
                
                # Clear license cache
                license_manager.clear_cache()
                
                messages.success(request, "Open Source license selected. Licensing messages have been removed.")
                return redirect('booking:license_status')
                
        except Exception as e:
            logger.error(f"Open source license selection failed: {e}")
            messages.error(request, f"Failed to select open source license: {e}")
    
    context = {
        'current_license': license_manager.get_current_license(),
    }
    
    return render(request, 'licensing/select_open_source.html', context)


@staff_member_required
def license_activate(request):
    """Activate a license key."""
    if request.method == 'POST':
        form = LicenseActivationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Deactivate any existing licenses
                    LicenseConfiguration.objects.filter(is_active=True).update(is_active=False)
                    
                    # Create new license configuration
                    license_config = LicenseConfiguration.objects.create(
                        license_key=form.cleaned_data['license_key'],
                        license_type='basic_commercial',  # Default for manual activation
                        organization_name=form.cleaned_data['organization_name'],
                        organization_slug=form.cleaned_data['organization_name'].lower().replace(' ', '-'),
                        contact_email=form.cleaned_data['contact_email'],
                        is_active=True
                    )
                    
                    # Create default branding configuration
                    BrandingConfiguration.objects.create(
                        license=license_config,
                        company_name=form.cleaned_data['organization_name'],
                        email_from_name=form.cleaned_data['organization_name'],
                    )
                    
                    # Clear license cache
                    license_manager.clear_cache()
                    
                    messages.success(request, f"License activated successfully for {license_config.organization_name}")
                    return redirect('booking:site_admin_license_management')
                    
            except Exception as e:
                logger.error(f"License activation failed: {e}")
                messages.error(request, f"License activation failed: {e}")
    else:
        form = LicenseActivationForm()
    
    return render(request, 'licensing/activate.html', {'form': form})


@staff_member_required
def license_configure(request):
    """Configure license and branding settings."""
    license_config = license_manager.get_current_license()
    
    if not license_config:
        messages.error(request, "No active license found. Please activate a license first.")
        return redirect('booking:license_activate')
    
    # Get or create branding configuration
    try:
        branding_config = license_config.branding
    except BrandingConfiguration.DoesNotExist:
        branding_config = BrandingConfiguration(license=license_config)
    
    if request.method == 'POST':
        form = BrandingConfigurationForm(request.POST, request.FILES, instance=branding_config)
        if form.is_valid():
            form.save()
            license_manager.clear_cache()
            messages.success(request, "Branding configuration updated successfully")
            return redirect('booking:site_admin_license_management')
    else:
        form = BrandingConfigurationForm(instance=branding_config)
    
    context = {
        'form': form,
        'license_config': license_config,
        'branding_config': branding_config,
    }
    
    return render(request, 'licensing/configure.html', context)


@staff_member_required
def license_validation_logs(request):
    """View license validation logs."""
    license_config = license_manager.get_current_license()
    
    if not license_config:
        messages.error(request, "No active license found.")
        return redirect('booking:site_admin_license_management')
    
    logs = license_config.validation_logs.all()
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'license_config': license_config,
        'page_obj': page_obj,
        'logs': page_obj,
    }
    
    return render(request, 'licensing/validation_logs.html', context)


@staff_member_required
@require_http_methods(["POST"])
def license_validate_now(request):
    """Manually trigger license validation."""
    try:
        is_valid, error_msg = license_manager.validate_license(force_remote=True)
        
        if is_valid:
            messages.success(request, "License validation successful")
        else:
            messages.error(request, f"License validation failed: {error_msg}")
            
    except Exception as e:
        logger.error(f"Manual license validation failed: {e}")
        messages.error(request, f"License validation error: {e}")
    
    return redirect('booking:site_admin_license_management')


@csrf_exempt
def license_api_status(request):
    """API endpoint for license status (for remote monitoring)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        license_info = license_manager.get_license_info()
        
        # Remove sensitive information for API response
        api_response = {
            'license_type': license_info.get('type'),
            'is_valid': license_info.get('is_valid'),
            'organization': license_info.get('organization'),
            'expires_at': license_info.get('expires_at').isoformat() if license_info.get('expires_at') else None,
            'last_validation': license_info.get('last_validation').isoformat() if license_info.get('last_validation') else None,
            'features': license_info.get('features', {}),
        }
        
        return JsonResponse(api_response)
        
    except Exception as e:
        logger.error(f"License API status error: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


def generate_license_key_view(request):
    """Generate a new license key (for development/testing)."""
    if not settings.DEBUG:
        return HttpResponse("Not available in production", status=403)
    
    if request.method == 'POST':
        org_name = request.POST.get('organization', 'Test Organization')
        license_type = request.POST.get('license_type', 'basic_commercial')
        
        license_key = license_manager.generate_license_key(org_name, license_type)
        
        return JsonResponse({
            'license_key': license_key,
            'organization': org_name,
            'license_type': license_type,
        })
    
    return render(request, 'licensing/generate_key.html')