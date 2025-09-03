# Generated manually for booking.0009_add_requires_risk_assessment_field
# TEMPORARILY DISABLED - uncomment when django-apscheduler is installed

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0008_add_risk_assessment_prerequisite'),
    ]

    operations = [
        migrations.AddField(
            model_name='resource',
            name='requires_risk_assessment',
            field=models.BooleanField(default=False, help_text='Require users to complete a risk assessment before accessing this resource'),
        ),
    ]