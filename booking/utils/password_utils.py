# booking/utils/password_utils.py
"""
Password complexity validation utilities.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import re
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    """
    Validate password complexity requirements.
    """
    
    def __init__(self, 
                 min_length=8,
                 require_uppercase=True,
                 require_lowercase=True, 
                 require_digits=True,
                 require_symbols=True,
                 min_unique_chars=4):
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digits = require_digits
        self.require_symbols = require_symbols
        self.min_unique_chars = min_unique_chars

    def validate(self, password, user=None):
        """
        Validate password complexity.
        
        Args:
            password: Password to validate
            user: User instance (optional)
            
        Raises:
            ValidationError: If password doesn't meet requirements
        """
        errors = []

        # Check minimum length
        if len(password) < self.min_length:
            errors.append(
                _('Password must be at least %(min_length)d characters long.') % {
                    'min_length': self.min_length
                }
            )

        # Check uppercase requirement
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append(_('Password must contain at least one uppercase letter.'))

        # Check lowercase requirement
        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append(_('Password must contain at least one lowercase letter.'))

        # Check digit requirement
        if self.require_digits and not re.search(r'[0-9]', password):
            errors.append(_('Password must contain at least one digit.'))

        # Check symbol requirement
        if self.require_symbols and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append(_('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>).'))

        # Check unique characters
        if len(set(password)) < self.min_unique_chars:
            errors.append(
                _('Password must contain at least %(min_unique)d unique characters.') % {
                    'min_unique': self.min_unique_chars
                }
            )

        # Check for common patterns
        self._check_common_patterns(password, errors, user)

        if errors:
            raise ValidationError(errors)

    def _check_common_patterns(self, password, errors, user):
        """Check for common password patterns to avoid."""
        
        # Check for sequential characters
        if re.search(r'(012|123|234|345|456|567|678|789|890)', password):
            errors.append(_('Password cannot contain sequential numbers.'))
        
        if re.search(r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
            errors.append(_('Password cannot contain sequential letters.'))

        # Check for repeated characters (more than 2 consecutive)
        if re.search(r'(.)\1{2,}', password):
            errors.append(_('Password cannot contain more than 2 consecutive identical characters.'))

        # Check keyboard patterns
        keyboard_patterns = [
            'qwerty', 'qwertz', 'azerty', 'dvorak',
            'asdf', 'zxcv', 'hjkl', 'uiop',
            '1234', '4321', 'abcd', 'dcba'
        ]
        
        for pattern in keyboard_patterns:
            if pattern in password.lower():
                errors.append(_('Password cannot contain common keyboard patterns.'))
                break

        # Check against user information if provided
        if user:
            self._check_user_info_in_password(password, errors, user)

    def _check_user_info_in_password(self, password, errors, user):
        """Check if password contains user information."""
        password_lower = password.lower()
        
        # Check username
        if user.username and len(user.username) >= 3 and user.username.lower() in password_lower:
            errors.append(_('Password cannot contain your username.'))

        # Check first/last name
        if user.first_name and len(user.first_name) >= 3 and user.first_name.lower() in password_lower:
            errors.append(_('Password cannot contain your first name.'))
            
        if user.last_name and len(user.last_name) >= 3 and user.last_name.lower() in password_lower:
            errors.append(_('Password cannot contain your last name.'))

        # Check email parts
        if user.email:
            email_parts = user.email.split('@')[0]
            if len(email_parts) >= 3 and email_parts.lower() in password_lower:
                errors.append(_('Password cannot contain parts of your email address.'))

    def get_help_text(self):
        """Return help text for password requirements."""
        requirements = []
        
        requirements.append(f"At least {self.min_length} characters long")
        
        if self.require_uppercase:
            requirements.append("At least one uppercase letter")
            
        if self.require_lowercase:
            requirements.append("At least one lowercase letter")
            
        if self.require_digits:
            requirements.append("At least one digit")
            
        if self.require_symbols:
            requirements.append("At least one special character")
            
        requirements.append(f"At least {self.min_unique_chars} unique characters")
        requirements.append("Cannot contain sequential characters, keyboard patterns, or personal information")
        
        return _("Password must meet the following requirements: ") + "; ".join(requirements) + "."


class CommonPasswordValidator:
    """
    Validator to check against common passwords list.
    """
    
    def __init__(self):
        # Common passwords to explicitly block
        self.common_passwords = {
            'password', 'password123', '123456', '123456789', 'qwerty',
            'abc123', 'password1', 'admin', 'administrator', 'root',
            'user', 'guest', 'test', 'demo', 'welcome', 'login',
            'passw0rd', 'p@ssword', 'p@ssw0rd', '1qaz2wsx', 'qwertyuiop',
            'asdfghjkl', 'zxcvbnm', 'letmein', 'monkey', 'dragon',
            'sunshine', 'princess', 'football', 'baseball', 'welcome123'
        }

    def validate(self, password, user=None):
        """Validate password against common passwords."""
        if password.lower() in self.common_passwords:
            raise ValidationError(
                _('This password is too common. Please choose a more unique password.'),
                code='password_too_common',
            )

    def get_help_text(self):
        return _('Your password cannot be a commonly used password.')


def get_password_strength_score(password):
    """
    Calculate password strength score (0-100).
    
    Args:
        password: Password to analyze
        
    Returns:
        dict: Score and feedback
    """
    score = 0
    feedback = []
    
    # Length scoring (0-30 points)
    length = len(password)
    if length >= 12:
        score += 30
        feedback.append("✓ Good length")
    elif length >= 8:
        score += 20
        feedback.append("⚠ Adequate length")
    else:
        score += 10
        feedback.append("✗ Too short")
    
    # Character variety (0-40 points)
    has_lower = bool(re.search(r'[a-z]', password))
    has_upper = bool(re.search(r'[A-Z]', password))
    has_digit = bool(re.search(r'[0-9]', password))
    has_symbol = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
    
    variety_score = sum([has_lower, has_upper, has_digit, has_symbol])
    score += variety_score * 10
    
    if variety_score >= 4:
        feedback.append("✓ Excellent character variety")
    elif variety_score >= 3:
        feedback.append("⚠ Good character variety")
    else:
        feedback.append("✗ Poor character variety")
    
    # Uniqueness (0-20 points)
    unique_chars = len(set(password))
    if unique_chars >= len(password) * 0.75:
        score += 20
        feedback.append("✓ Good character uniqueness")
    elif unique_chars >= len(password) * 0.5:
        score += 10
        feedback.append("⚠ Adequate character uniqueness")
    else:
        feedback.append("✗ Too many repeated characters")
    
    # Penalty for common patterns (0-10 points deduction)
    if re.search(r'(012|123|234|345|456|567|678|789|890)', password):
        score -= 5
        feedback.append("✗ Contains sequential numbers")
        
    if re.search(r'(.)\1{2,}', password):
        score -= 5
        feedback.append("✗ Contains repeated characters")
    
    # Ensure score is between 0-100
    score = max(0, min(100, score))
    
    # Determine strength level
    if score >= 80:
        strength = "Very Strong"
        color = "success"
    elif score >= 60:
        strength = "Strong"
        color = "primary"
    elif score >= 40:
        strength = "Medium"
        color = "warning"
    else:
        strength = "Weak"
        color = "danger"
    
    return {
        'score': score,
        'strength': strength,
        'color': color,
        'feedback': feedback
    }


def check_password_against_breaches(password_hash):
    """
    Check if password hash appears in known data breaches.
    This is a placeholder for future integration with HaveIBeenPwned API.
    
    Args:
        password_hash: SHA-1 hash of password
        
    Returns:
        dict: Breach status and count
    """
    # Placeholder implementation
    # In production, this would check against HaveIBeenPwned API
    return {
        'is_breached': False,
        'breach_count': 0,
        'checked': False,
        'message': 'Breach checking not implemented yet'
    }


def generate_password_requirements_html():
    """
    Generate HTML for password requirements display.
    
    Returns:
        str: HTML string with password requirements
    """
    min_length = getattr(settings, 'AUTH_PASSWORD_MIN_LENGTH', 8)
    
    html = f"""
    <div class="password-requirements">
        <h6>Password Requirements:</h6>
        <ul class="list-unstyled small">
            <li><i class="bi bi-check-circle text-muted"></i> At least {min_length} characters</li>
            <li><i class="bi bi-check-circle text-muted"></i> At least one uppercase letter (A-Z)</li>
            <li><i class="bi bi-check-circle text-muted"></i> At least one lowercase letter (a-z)</li>
            <li><i class="bi bi-check-circle text-muted"></i> At least one number (0-9)</li>
            <li><i class="bi bi-check-circle text-muted"></i> At least one special character (!@#$%^&*)</li>
            <li><i class="bi bi-check-circle text-muted"></i> No personal information (name, email, username)</li>
            <li><i class="bi bi-check-circle text-muted"></i> No common patterns or dictionary words</li>
        </ul>
    </div>
    """
    
    return html