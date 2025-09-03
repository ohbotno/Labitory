# Generated manually for resource close functionality

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('booking', '0010_add_assessment_file_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='resource',
            name='is_closed',
            field=models.BooleanField(default=False, help_text='Temporarily close this resource to prevent new bookings'),
        ),
        migrations.AddField(
            model_name='resource',
            name='closed_reason',
            field=models.TextField(blank=True, help_text='Reason for closing the resource (optional)'),
        ),
        migrations.AddField(
            model_name='resource',
            name='closed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='resource',
            name='closed_by',
            field=models.ForeignKey(blank=True, help_text='User who closed the resource', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='closed_resources', to=settings.AUTH_USER_MODEL),
        ),
    ]