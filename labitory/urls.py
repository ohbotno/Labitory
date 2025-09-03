# labitory/urls.py
"""
URL configuration for labitory project.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView
from booking.forms import CustomAuthenticationForm
from booking.views import CustomLoginView

urlpatterns = [
    # Favicon routes with cache busting
    path('favicon.ico', RedirectView.as_view(url='/static/images/favicon.ico?v=2', permanent=True)),
    path('favicon.png', RedirectView.as_view(url='/static/images/favicon.png?v=2', permanent=True)),
    
    path('admin/', admin.site.urls),
    # Custom login view with our form and first login logic
    path('accounts/login/', CustomLoginView.as_view(authentication_form=CustomAuthenticationForm), name='login'),
    # Include other auth URLs
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/', include('booking.api_urls')),
    path('', include('booking.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)