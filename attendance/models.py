from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import face_recognition
import pickle
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ==================== ORGANIZATION MODELS ====================

class Organization(models.Model):
    INDUSTRY_CHOICES = [
        ('IT', 'Information Technology'),
        ('EDU', 'Education'),
        ('FIN', 'Finance'),
        ('HLTH', 'Healthcare'),
        ('OTHER', 'Other'),
    ]
    SIZE_CHOICES = [
        ('small', 'Small (1-50 employees)'),
        ('medium', 'Medium (51-200 employees)'),
        ('large', 'Large (201+ employees)'),
    ]
    
    name = models.CharField(_('name'), max_length=100, unique=True)
    industry = models.CharField(_('industry'), max_length=20, choices=INDUSTRY_CHOICES)
    size = models.CharField(_('size'), max_length=20, choices=SIZE_CHOICES, blank=True, null=True)  
    address = models.TextField(_('address'))
    logo = models.ImageField(_('logo'), upload_to='logos/', blank=True, null=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')

    def __str__(self):
        return self.name


class Department(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='departments',
        verbose_name=_('organization')
    )
    name = models.CharField(_('name'), max_length=100)
    code = models.CharField(_('code'), max_length=10)
    description = models.TextField(_('description'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        verbose_name = _('department')
        verbose_name_plural = _('departments')
        unique_together = ('organization', 'name')

    def __str__(self):
        return f"{self.name} ({self.code})"


# ==================== USER MANAGEMENT ====================

class UserManager(BaseUserManager):
    """Custom manager for email-based authentication"""

    def create_user(self, email, first_name, last_name, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Users must have an email address'))

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('position', 'ADMIN')
        return self.create_user(email, first_name, last_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with extended fields"""
    POSITION_CHOICES = [
        ('STAFF', 'Staff'),
        ('HOD', 'Head of Department'),
        ('MANAGER', 'Manager'),
        ('ADMIN', 'Administrator'),
        ('DIRECTOR', 'Director/CEO')
    ]

    # Basic information
    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=30)
    last_name = models.CharField(_('last name'), max_length=30)

    # Organizational information
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name='users',
        verbose_name=_('organization'),
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('department')
    )
    position = models.CharField(
        _('position'),
        max_length=20,
        choices=POSITION_CHOICES,
        default='STAFF'
    )

    # Contact information
    phone = models.CharField(_('phone number'), max_length=20, blank=True)
    profile_picture = models.ImageField(
        _('profile picture'),
        upload_to='profile_pics/',
        null=True,
        blank=True
    )

    # Status flags
    is_verified = models.BooleanField(_('verified'), default=False)
    is_staff = models.BooleanField(_('staff status'), default=False)
    is_active = models.BooleanField(_('active'), default=True)

    # Tracking information
    last_login_ip = models.GenericIPAddressField(_('last login IP'), null=True, blank=True)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_short_name(self):
        return self.first_name

    @property
    def username(self):
        """Backward compatibility for username field"""
        return self.email

    @property
    def is_admin(self):
        return self.position in ['ADMIN', 'DIRECTOR']

    @property
    def is_hod(self):
        return self.position == 'HOD'


class Profile(models.Model):
    """Extended user profile information"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_('user')
    )
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        null=True
    )
    address = models.TextField(
        _('address'),
        blank=True,
        null=True
    )
    date_of_birth = models.DateField(
        _('date of birth'),
        blank=True,
        null=True
    )
    emergency_contact = models.CharField(
        _('emergency contact'),
        max_length=100,
        blank=True,
        null=True
    )
    emergency_phone = models.CharField(
        _('emergency phone'),
        max_length=20,
        blank=True,
        null=True
    )
    position = models.CharField(
        _('position'),
        max_length=100,
        blank=True,
        null=True
    )
    hire_date = models.DateField(
        _('hire date'),
        blank=True,
        null=True
    )
    profile_picture = models.ImageField(
        _('profile picture'),
        upload_to='profile_pics/',
        blank=True,
        null=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('profile')
        verbose_name_plural = _('profiles')

    def __str__(self):
        return f"{self.user.get_full_name()}'s Profile"


class FaceProfile(models.Model):
    """Face recognition profile with enhanced validation"""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='face_profile',
        verbose_name=_('user')
    )
    face_encoding = models.BinaryField(
        _('face encoding'),
        null=True,
        blank=True,
        help_text=_("Facial recognition data")
    )
    image = models.ImageField(
        _('image'),
        upload_to='face_profiles/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        help_text=_("High-quality frontal face image")
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_("Designates whether this face profile should be treated as active")
    )
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )
    last_used = models.DateTimeField(
        _('last used'),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _('face profile')
        verbose_name_plural = _('face profiles')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Face Profile for {self.user.get_full_name()}"

    def save(self, *args, **kwargs):
        """Override save to handle face encoding"""
        if self.image and (not self.face_encoding or not self.pk):
            try:
                image = face_recognition.load_image_file(self.image.file)
                face_locations = face_recognition.face_locations(image)

                if not face_locations:
                    raise ValueError(_("No faces detected in the image"))

                if len(face_locations) > 1:
                    raise ValueError(_("Multiple faces detected in the image"))

                face_encoding = face_recognition.face_encodings(image, face_locations)[0]
                self.face_encoding = pickle.dumps(face_encoding)

            except Exception as e:
                logger.error(f"Error processing face image: {str(e)}")
                raise

        super().save(*args, **kwargs)


# ==================== ATTENDANCE MODELS ====================

class Attendance(models.Model):
    """Employee attendance records"""
    STATUS_CHOICES = (
        ('PRESENT', _('Present')),
        ('LATE', _('Late')),
        ('ABSENT', _('Absent')),
        ('ON_LEAVE', _('On Leave')),
    )

    METHOD_CHOICES = (
        ('FACE', _('Face Recognition')),
        ('MANUAL', _('Manual Entry')),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='attendances',
        verbose_name=_('user')
    )
    date = models.DateField(_('date'), default=timezone.now)
    time_in = models.TimeField(_('time in'))
    time_out = models.TimeField(_('time out'), null=True, blank=True)
    status = models.CharField(
        _('status'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='PRESENT'
    )
    method = models.CharField(
        _('method'),
        max_length=10,
        choices=METHOD_CHOICES,
        default='FACE'
    )
    location = models.CharField(_('location'), max_length=100, blank=True)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        verbose_name = _('attendance')
        verbose_name_plural = _('attendances')
        unique_together = ('user', 'date')
        ordering = ['-date', '-time_in']

    def __str__(self):
        return f"{self.user} - {self.date} ({self.status})"

    def duration(self):
        if self.time_out:
            time_in_dt = datetime.combine(self.date, self.time_in)
            time_out_dt = datetime.combine(self.date, self.time_out)
            delta = time_out_dt - time_in_dt
            return delta.total_seconds() / 3600  # Return hours
        return None

    def get_duration_display(self):
        duration = self.duration()
        if duration is not None:
            hours = int(duration)
            minutes = int((duration - hours) * 60)
            return f"{hours}h {minutes}m"
        return "--"


class AttendanceReport(models.Model):
    """Generated attendance reports"""
    REPORT_TYPES = (
        ('DAILY', _('Daily Report')),
        ('WEEKLY', _('Weekly Report')),
        ('MONTHLY', _('Monthly Report')),
        ('CUSTOM', _('Custom Date Range')),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name=_('user')
    )
    report_type = models.CharField(
        _('report type'),
        max_length=10,
        choices=REPORT_TYPES
    )
    start_date = models.DateField(
        _('start date')
    )
    end_date = models.DateField(
        _('end date')
    )
    record_count = models.PositiveIntegerField(
        _('record count'),
        default=0
    )
    generated_at = models.DateTimeField(
        _('generated at'),
        auto_now_add=True
    )
    file = models.FileField(
        _('file'),
        upload_to='reports/',
        blank=True,
        null=True
    )
    parameters = models.JSONField(
        _('parameters'),
        default=dict,
        blank=True
    )

    class Meta:
        verbose_name = _('attendance report')
        verbose_name_plural = _('attendance reports')
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_report_type_display()} ({self.start_date} to {self.end_date})"

    def save(self, *args, **kwargs):
        """Add additional processing before saving"""
        if not self.parameters:
            self.parameters = {
                'report_type': self.report_type,
                'date_range': f"{self.start_date} to {self.end_date}",
                'record_count': self.record_count
            }
        super().save(*args, **kwargs)


# ==================== AI MODELS ====================

class AIMessage(models.Model):
    """AI-generated messages for users"""
    CATEGORY_CHOICES = [
        ('MOTIVATION', 'Motivational Quote'),
        ('JOKE', 'Funny Joke'),
        ('TIP', 'Productivity Tip'),
    ]

    SOURCE_CHOICES = [
        ('SYSTEM', 'System Generated'),
        ('OPENAI', 'OpenAI API'),
        ('USER', 'User Provided'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_messages',
        verbose_name=_('user')
    )
    content = models.TextField(_('content'))
    category = models.CharField(
        _('category'),
        max_length=20,
        choices=CATEGORY_CHOICES
    )
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    source = models.CharField(
        _('source'),
        max_length=20,
        choices=SOURCE_CHOICES,
        default='SYSTEM'
    )

    class Meta:
        verbose_name = _('AI message')
        verbose_name_plural = _('AI messages')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_category_display()} for {self.user or 'All Users'}"


class AIFeedback(models.Model):
    """User feedback for AI messages"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ai_feedbacks',
        verbose_name=_('user')
    )
    message = models.TextField(
        _('message'),
        blank=True
    )
    is_positive = models.BooleanField(
        _('is positive'),
        help_text=_("Was the feedback positive?")
    )
    feedback_text = models.TextField(
        _('feedback text'),
        blank=True
    )
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('AI feedback')
        verbose_name_plural = _('AI feedbacks')
        ordering = ['-created_at']

    def __str__(self):
        return f"{'Positive' if self.is_positive else 'Negative'} feedback from {self.user}"