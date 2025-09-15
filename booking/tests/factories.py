"""Test factories for creating test data."""
import factory
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from booking.models import (
    UserProfile, Resource, Booking, BookingTemplate, 
    ApprovalRule, Maintenance, BookingHistory,
    Faculty, College, Department, AccessRequest, ResourceAccess
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True


class FacultyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Faculty
    
    name = factory.Faker('word')
    code = factory.Sequence(lambda n: f"FAC{n}")
    is_active = True


class CollegeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = College
    
    name = factory.Faker('word')
    code = factory.Sequence(lambda n: f"COL{n}")
    faculty = factory.SubFactory(FacultyFactory)
    is_active = True


class DepartmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Department
    
    name = factory.Faker('word')
    code = factory.Sequence(lambda n: f"DEP{n}")
    college = factory.SubFactory(CollegeFactory)
    is_active = True


class UserProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserProfile
        django_get_or_create = ('user',)
        skip_postgeneration_save = True
    
    user = factory.SubFactory(UserFactory)
    role = 'student'
    group = factory.Faker('word')
    
    # Create academic hierarchy with proper relationships
    faculty = factory.SubFactory(FacultyFactory)
    college = factory.SubFactory(CollegeFactory, faculty=factory.SelfAttribute('..faculty'))
    department = factory.SubFactory(DepartmentFactory, college=factory.SelfAttribute('..college'))
    
    student_level = 'undergraduate'
    training_level = 1
    is_inducted = True
    email_verified = True
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override creation to handle existing profiles from signals."""
        user = kwargs.get('user')
        if user:
            # Check if profile already exists from signal
            try:
                profile = model_class.objects.get(user=user)
                # Update existing profile with factory data
                for key, value in kwargs.items():
                    if key != 'user':
                        setattr(profile, key, value)
                profile.save()
                return profile
            except model_class.DoesNotExist:
                pass
        
        return super()._create(model_class, *args, **kwargs)
    
    @factory.post_generation
    def set_role_specific_fields(obj, create, extracted, **kwargs):
        """Set role-specific fields based on role."""
        if obj.role == 'student':
            obj.student_id = f"STU{obj.id or 1000}"
            if not obj.student_level:
                obj.student_level = 'undergraduate'
        elif obj.role in ['researcher', 'academic', 'technician', 'sysadmin']:
            obj.staff_number = f"STAFF{obj.id or 1000}"
            obj.student_level = None
            obj.student_id = None
        
        if create:
            obj.save()


class ResourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Resource
    
    name = factory.Faker('word')
    resource_type = 'instrument'
    description = factory.Faker('text', max_nb_chars=200)
    location = factory.Faker('address')
    capacity = 1
    required_training_level = 1
    requires_induction = False
    max_booking_hours = 8
    is_active = True


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking
    
    user = factory.SubFactory(UserFactory)
    resource = factory.SubFactory(ResourceFactory)
    title = factory.Faker('sentence', nb_words=4)
    description = factory.Faker('text', max_nb_chars=100)
    start_time = factory.LazyFunction(
        lambda: timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=2)
    )
    end_time = factory.LazyAttribute(lambda obj: obj.start_time + timedelta(hours=2))
    status = 'pending'


class BookingTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingTemplate
    
    user = factory.SubFactory(UserFactory)
    name = factory.Faker('sentence', nb_words=3)
    description_template = factory.Faker('text', max_nb_chars=100)
    resource = factory.SubFactory(ResourceFactory)
    duration_hours = 2
    duration_minutes = 0


class ApprovalRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ApprovalRule
    
    name = factory.Faker('sentence', nb_words=3)
    resource = factory.SubFactory(ResourceFactory)
    approval_type = 'auto'
    conditions = {}
    user_roles = []


class MaintenanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Maintenance
    
    resource = factory.SubFactory(ResourceFactory)
    title = factory.Faker('sentence', nb_words=4)
    description = factory.Faker('text', max_nb_chars=100)
    start_time = factory.LazyFunction(lambda: timezone.now() + timedelta(days=2))
    end_time = factory.LazyAttribute(lambda obj: obj.start_time + timedelta(hours=4))
    maintenance_type = 'scheduled'
    created_by = factory.SubFactory(UserFactory)


class BookingHistoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookingHistory
    
    booking = factory.SubFactory(BookingFactory)
    user = factory.SubFactory(UserFactory)
    action = 'created'
    details = {}


class AccessRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccessRequest
    
    user = factory.SubFactory(UserFactory)
    resource = factory.SubFactory(ResourceFactory)
    access_type = 'book'
    justification = factory.Faker('text', max_nb_chars=200)
    status = 'pending'


class ResourceAccessFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ResourceAccess
    
    resource = factory.SubFactory(ResourceFactory)
    user = factory.SubFactory(UserFactory)
    access_type = 'book'
    granted_by = factory.SubFactory(UserFactory)
    is_active = True


