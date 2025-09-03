# booking/views/modules/hierarchy.py
"""
Academic hierarchy management views for the Aperture Booking system.

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
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator

from ...models import Faculty, College, Department


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_academic_hierarchy_view(request):
    """Academic hierarchy management dashboard."""
    faculties = Faculty.objects.annotate(
        colleges_count=Count('colleges'),
        departments_count=Count('colleges__departments')
    ).order_by('name')
    
    colleges = College.objects.select_related('faculty').annotate(
        departments_count=Count('departments')
    ).order_by('faculty__name', 'name')
    
    departments = Department.objects.select_related('college__faculty').order_by(
        'college__faculty__name', 'college__name', 'name'
    )
    
    stats = {
        'total_faculties': Faculty.objects.count(),
        'active_faculties': Faculty.objects.filter(is_active=True).count(),
        'total_colleges': College.objects.count(),
        'active_colleges': College.objects.filter(is_active=True).count(),
        'total_departments': Department.objects.count(),
        'active_departments': Department.objects.filter(is_active=True).count(),
    }
    
    return render(request, 'booking/site_admin_academic_hierarchy.html', {
        'faculties': faculties[:10],  # Show first 10 for overview
        'colleges': colleges[:10],    # Show first 10 for overview
        'departments': departments[:10],  # Show first 10 for overview
        'stats': stats,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_faculties_view(request):
    """Faculty management view."""
    faculties = Faculty.objects.annotate(
        colleges_count=Count('colleges'),
        departments_count=Count('colleges__departments')
    ).order_by('name')
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        faculties = faculties.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(faculties, 20)
    page = request.GET.get('page')
    faculties = paginator.get_page(page)
    
    return render(request, 'booking/site_admin_faculties.html', {
        'faculties': faculties,
        'search': search,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_faculty_create_view(request):
    """Create new faculty."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code:
            messages.error(request, 'Faculty name and code are required.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': None,
                'action': 'Create',
            })
        
        if Faculty.objects.filter(name=name).exists():
            messages.error(request, 'A faculty with this name already exists.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': None,
                'action': 'Create',
            })
        
        if Faculty.objects.filter(code=code).exists():
            messages.error(request, 'A faculty with this code already exists.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': None,
                'action': 'Create',
            })
        
        faculty = Faculty.objects.create(
            name=name,
            code=code,
            is_active=is_active
        )
        
        messages.success(request, f'Faculty "{faculty.name}" created successfully.')
        return redirect('booking:site_admin_faculties')
    
    return render(request, 'booking/site_admin_faculty_form.html', {
        'faculty': None,
        'action': 'Create',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_faculty_edit_view(request, faculty_id):
    """Edit existing faculty."""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code:
            messages.error(request, 'Faculty name and code are required.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': faculty,
                'action': 'Edit',
            })
        
        # Check for duplicate name (excluding current faculty)
        if Faculty.objects.filter(name=name).exclude(id=faculty.id).exists():
            messages.error(request, 'A faculty with this name already exists.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': faculty,
                'action': 'Edit',
            })
        
        # Check for duplicate code (excluding current faculty)
        if Faculty.objects.filter(code=code).exclude(id=faculty.id).exists():
            messages.error(request, 'A faculty with this code already exists.')
            return render(request, 'booking/site_admin_faculty_form.html', {
                'faculty': faculty,
                'action': 'Edit',
            })
        
        faculty.name = name
        faculty.code = code
        faculty.is_active = is_active
        faculty.save()
        
        messages.success(request, f'Faculty "{faculty.name}" updated successfully.')
        return redirect('booking:site_admin_faculties')
    
    return render(request, 'booking/site_admin_faculty_form.html', {
        'faculty': faculty,
        'action': 'Edit',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_faculty_delete_view(request, faculty_id):
    """Delete faculty."""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    
    if request.method == 'POST':
        faculty_name = faculty.name
        try:
            faculty.delete()
            messages.success(request, f'Faculty "{faculty_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Cannot delete faculty: {str(e)}')
        
        return redirect('booking:site_admin_faculties')
    
    # Get related data for confirmation
    colleges_count = faculty.colleges.count()
    departments_count = Department.objects.filter(college__faculty=faculty).count()
    
    return render(request, 'booking/site_admin_faculty_confirm_delete.html', {
        'faculty': faculty,
        'colleges_count': colleges_count,
        'departments_count': departments_count,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_colleges_view(request):
    """College management view."""
    colleges = College.objects.select_related('faculty').annotate(
        departments_count=Count('departments')
    ).order_by('faculty__name', 'name')
    
    # Filter by faculty
    faculty_id = request.GET.get('faculty')
    selected_faculty_obj = None
    if faculty_id:
        try:
            selected_faculty_obj = Faculty.objects.get(id=faculty_id)
            colleges = colleges.filter(faculty_id=faculty_id)
        except Faculty.DoesNotExist:
            faculty_id = None
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        colleges = colleges.filter(
            Q(name__icontains=search) | 
            Q(code__icontains=search) |
            Q(faculty__name__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(colleges, 20)
    page = request.GET.get('page')
    colleges = paginator.get_page(page)
    
    faculties = Faculty.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/site_admin_colleges.html', {
        'colleges': colleges,
        'faculties': faculties,
        'search': search,
        'selected_faculty': faculty_id,
        'selected_faculty_obj': selected_faculty_obj,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_college_create_view(request):
    """Create new college."""
    faculties = Faculty.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        faculty_id = request.POST.get('faculty')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code or not faculty_id:
            messages.error(request, 'College name, code, and faculty are required.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': None,
                'faculties': faculties,
                'action': 'Create',
            })
        
        try:
            faculty = Faculty.objects.get(id=faculty_id)
        except Faculty.DoesNotExist:
            messages.error(request, 'Selected faculty does not exist.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': None,
                'faculties': faculties,
                'action': 'Create',
            })
        
        # Check for duplicate name within faculty
        if College.objects.filter(faculty=faculty, name=name).exists():
            messages.error(request, 'A college with this name already exists in this faculty.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': None,
                'faculties': faculties,
                'action': 'Create',
            })
        
        # Check for duplicate code within faculty
        if College.objects.filter(faculty=faculty, code=code).exists():
            messages.error(request, 'A college with this code already exists in this faculty.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': None,
                'faculties': faculties,
                'action': 'Create',
            })
        
        college = College.objects.create(
            name=name,
            code=code,
            faculty=faculty,
            is_active=is_active
        )
        
        messages.success(request, f'College "{college.name}" created successfully.')
        return redirect('booking:site_admin_colleges')
    
    return render(request, 'booking/site_admin_college_form.html', {
        'college': None,
        'faculties': faculties,
        'action': 'Create',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_college_edit_view(request, college_id):
    """Edit existing college."""
    college = get_object_or_404(College, id=college_id)
    faculties = Faculty.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        faculty_id = request.POST.get('faculty')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code or not faculty_id:
            messages.error(request, 'College name, code, and faculty are required.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': college,
                'faculties': faculties,
                'action': 'Edit',
            })
        
        try:
            faculty = Faculty.objects.get(id=faculty_id)
        except Faculty.DoesNotExist:
            messages.error(request, 'Selected faculty does not exist.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': college,
                'faculties': faculties,
                'action': 'Edit',
            })
        
        # Check for duplicate name within faculty (excluding current college)
        if College.objects.filter(faculty=faculty, name=name).exclude(id=college.id).exists():
            messages.error(request, 'A college with this name already exists in this faculty.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': college,
                'faculties': faculties,
                'action': 'Edit',
            })
        
        # Check for duplicate code within faculty (excluding current college)
        if College.objects.filter(faculty=faculty, code=code).exclude(id=college.id).exists():
            messages.error(request, 'A college with this code already exists in this faculty.')
            return render(request, 'booking/site_admin_college_form.html', {
                'college': college,
                'faculties': faculties,
                'action': 'Edit',
            })
        
        college.name = name
        college.code = code
        college.faculty = faculty
        college.is_active = is_active
        college.save()
        
        messages.success(request, f'College "{college.name}" updated successfully.')
        return redirect('booking:site_admin_colleges')
    
    return render(request, 'booking/site_admin_college_form.html', {
        'college': college,
        'faculties': faculties,
        'action': 'Edit',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_college_delete_view(request, college_id):
    """Delete college."""
    college = get_object_or_404(College, id=college_id)
    
    if request.method == 'POST':
        college_name = college.name
        try:
            college.delete()
            messages.success(request, f'College "{college_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Cannot delete college: {str(e)}')
        
        return redirect('booking:site_admin_colleges')
    
    # Get related data for confirmation
    departments_count = college.departments.count()
    
    return render(request, 'booking/site_admin_college_confirm_delete.html', {
        'college': college,
        'departments_count': departments_count,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_departments_view(request):
    """Department management view."""
    departments = Department.objects.select_related('college__faculty').order_by(
        'college__faculty__name', 'college__name', 'name'
    )
    
    # Filter by faculty
    faculty_id = request.GET.get('faculty')
    selected_faculty_obj = None
    if faculty_id:
        try:
            selected_faculty_obj = Faculty.objects.get(id=faculty_id)
            departments = departments.filter(college__faculty_id=faculty_id)
        except Faculty.DoesNotExist:
            faculty_id = None
    
    # Filter by college
    college_id = request.GET.get('college')
    selected_college_obj = None
    if college_id:
        try:
            selected_college_obj = College.objects.get(id=college_id)
            departments = departments.filter(college_id=college_id)
        except College.DoesNotExist:
            college_id = None
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        departments = departments.filter(
            Q(name__icontains=search) | 
            Q(code__icontains=search) |
            Q(college__name__icontains=search) |
            Q(college__faculty__name__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(departments, 20)
    page = request.GET.get('page')
    departments = paginator.get_page(page)
    
    faculties = Faculty.objects.filter(is_active=True).order_by('name')
    colleges = College.objects.filter(is_active=True).select_related('faculty').order_by('faculty__name', 'name')
    
    return render(request, 'booking/site_admin_departments.html', {
        'departments': departments,
        'faculties': faculties,
        'colleges': colleges,
        'search': search,
        'selected_faculty': faculty_id,
        'selected_college': college_id,
        'selected_faculty_obj': selected_faculty_obj,
        'selected_college_obj': selected_college_obj,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_department_create_view(request):
    """Create new department."""
    colleges = College.objects.filter(is_active=True).select_related('faculty').order_by('faculty__name', 'name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        college_id = request.POST.get('college')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code or not college_id:
            messages.error(request, 'Department name, code, and college are required.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': None,
                'colleges': colleges,
                'action': 'Create',
            })
        
        try:
            college = College.objects.get(id=college_id)
        except College.DoesNotExist:
            messages.error(request, 'Selected college does not exist.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': None,
                'colleges': colleges,
                'action': 'Create',
            })
        
        # Check for duplicate name within college
        if Department.objects.filter(college=college, name=name).exists():
            messages.error(request, 'A department with this name already exists in this college.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': None,
                'colleges': colleges,
                'action': 'Create',
            })
        
        # Check for duplicate code within college
        if Department.objects.filter(college=college, code=code).exists():
            messages.error(request, 'A department with this code already exists in this college.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': None,
                'colleges': colleges,
                'action': 'Create',
            })
        
        department = Department.objects.create(
            name=name,
            code=code,
            college=college,
            is_active=is_active
        )
        
        messages.success(request, f'Department "{department.name}" created successfully.')
        return redirect('booking:site_admin_departments')
    
    return render(request, 'booking/site_admin_department_form.html', {
        'department': None,
        'colleges': colleges,
        'action': 'Create',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_department_edit_view(request, department_id):
    """Edit existing department."""
    department = get_object_or_404(Department, id=department_id)
    colleges = College.objects.filter(is_active=True).select_related('faculty').order_by('faculty__name', 'name')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        college_id = request.POST.get('college')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name or not code or not college_id:
            messages.error(request, 'Department name, code, and college are required.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': department,
                'colleges': colleges,
                'action': 'Edit',
            })
        
        try:
            college = College.objects.get(id=college_id)
        except College.DoesNotExist:
            messages.error(request, 'Selected college does not exist.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': department,
                'colleges': colleges,
                'action': 'Edit',
            })
        
        # Check for duplicate name within college (excluding current department)
        if Department.objects.filter(college=college, name=name).exclude(id=department.id).exists():
            messages.error(request, 'A department with this name already exists in this college.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': department,
                'colleges': colleges,
                'action': 'Edit',
            })
        
        # Check for duplicate code within college (excluding current department)
        if Department.objects.filter(college=college, code=code).exclude(id=department.id).exists():
            messages.error(request, 'A department with this code already exists in this college.')
            return render(request, 'booking/site_admin_department_form.html', {
                'department': department,
                'colleges': colleges,
                'action': 'Edit',
            })
        
        department.name = name
        department.code = code
        department.college = college
        department.is_active = is_active
        department.save()
        
        messages.success(request, f'Department "{department.name}" updated successfully.')
        return redirect('booking:site_admin_departments')
    
    return render(request, 'booking/site_admin_department_form.html', {
        'department': department,
        'colleges': colleges,
        'action': 'Edit',
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def site_admin_department_delete_view(request, department_id):
    """Delete department."""
    department = get_object_or_404(Department, id=department_id)
    
    if request.method == 'POST':
        department_name = department.name
        try:
            department.delete()
            messages.success(request, f'Department "{department_name}" deleted successfully.')
        except Exception as e:
            messages.error(request, f'Cannot delete department: {str(e)}')
        
        return redirect('booking:site_admin_departments')
    
    return render(request, 'booking/site_admin_department_confirm_delete.html', {
        'department': department,
    })