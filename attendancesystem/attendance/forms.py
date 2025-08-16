from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm
)
import re
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import FaceProfile, Department, Profile, Organization, User
import datetime
from django.urls import reverse_lazy
# from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class BaseForm(forms.Form):
    """Base form with common styling for all form fields."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if 'class' not in self.fields[field].widget.attrs:
                if isinstance(self.fields[field].widget, (forms.CheckboxInput, forms.RadioSelect)):
                    self.fields[field].widget.attrs['class'] = 'form-check-input'
                else:
                    self.fields[field].widget.attrs['class'] = 'form-control'


class EmailLoginForm(AuthenticationForm):
    """Custom authentication form using email as username."""
    
    username = forms.EmailField(
        label=_("Email Address"),
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'placeholder': 'your.email@example.com',
            'class': 'form-control-lg'
        })
    )
    
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': '••••••••',
            'class': 'form-control-lg'
        })
    )
    
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_("Remember me")
    )

    error_messages = {
        'invalid_login': _(
            "Please enter a correct email and password. Note that both "
            "fields may be case-sensitive."
        ),
        'inactive': _("This account is inactive."),
    }


class CustomSignupForm(UserCreationForm):
    """Enhanced user registration form with improved styling and UX"""
    
    # Personal Information Fields
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': _('John'),
            'autocomplete': 'given-name',
            'class': 'form-control form-control-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("First Name")
    )
    
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': _('Doe'),
            'autocomplete': 'family-name',
            'class': 'form-control form-control-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("Last Name")
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': _('your.email@example.com'),
            'autocomplete': 'email',
            'class': 'form-control form-control-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("Email Address")
    )
    
    # Organization Fields
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg py-3',
            'style': 'font-size: 1.1rem;',
            'hx-get': '/get-departments/',
            'hx-target': '#id_department',
            'hx-trigger': 'change'
        }),
        label=_("Organization"),
        help_text=_("Select your organization from the list")
    )
    
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg py-3',
            'style': 'font-size: 1.1rem;',
            'disabled': True
        }),
        label=_("Department"),
        help_text=_("Select your department (optional)")
    )
    
    position = forms.ChoiceField(
        choices=User.POSITION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("Position"),
        initial='STAFF'
    )
    
    # Password Fields
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': _('Create password'),
            'autocomplete': 'new-password',
            'class': 'form-control form-control-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("Password"),
        help_text=_("""
        <div class="password-requirements mt-2 p-3 bg-light rounded">
            <small class="text-muted">Password must contain:</small>
            <ul class="mb-0 ps-4">
                <li>At least 8 characters</li>
                <li>1 uppercase letter</li>
                <li>1 lowercase letter</li>
                <li>1 number</li>
            </ul>
        </div>
        """)
    )
    
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': _('Confirm password'),
            'autocomplete': 'new-password',
            'class': 'form-control form-control-lg py-3',
            'style': 'font-size: 1.1rem;'
        }),
        label=_("Password Confirmation")
    )
    
    # Terms and Conditions
    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input me-2',
            'style': 'width: 1.2rem; height: 1.2rem;'
        }),
        label=_("I agree to the terms and conditions"),
        error_messages={
            'required': _('You must accept the terms and conditions to register')
        }
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2', 
                 'organization', 'department', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize empty department queryset
        self.fields['department'].queryset = Department.objects.none()
        
        # If organization is in POST data, filter departments
        if 'organization' in self.data:
            try:
                org_id = int(self.data.get('organization'))
                departments = Department.objects.filter(organization_id=org_id).order_by('name')
                self.fields['department'].queryset = departments
                if departments.exists():
                    self.fields['department'].widget.attrs['disabled'] = False
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.organization:
            self.fields['department'].queryset = self.instance.organization.departments.all()
            self.fields['department'].widget.attrs['disabled'] = False

    def clean_email(self):
        """Validate that the email is unique and properly formatted."""
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("This email is already registered. Please use a different email."))
        return email
    
    def clean(self):
        """Validate organization-department relationship."""
        cleaned_data = super().clean()
        organization = cleaned_data.get('organization')
        department = cleaned_data.get('department')
        
        if department and department.organization != organization:
            self.add_error('department', 
                _("The selected department doesn't belong to the chosen organization"))
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the user with organization and department."""
        user = super().save(commit=False)
        user.organization = self.cleaned_data['organization']
        if self.cleaned_data.get('department'):
            user.department = self.cleaned_data['department']
        user.position = self.cleaned_data.get('position', 'STAFF')
        
        if commit:
            user.save()
            self.save_m2m()
        
        return user


class FaceRegistrationForm(forms.ModelForm):
    """Form for facial recognition registration."""
    
    image_data = forms.CharField(widget=forms.HiddenInput(), required=False)
    
    class Meta:
        model = FaceProfile
        fields = []
    
    def clean(self):
        """Validate that an image was captured."""
        cleaned_data = super().clean()
        if not cleaned_data.get('image_data'):
            raise forms.ValidationError("Please capture your face image")
        return cleaned_data


class AttendanceForm(BaseForm):
    """Form for recording attendance."""
    
    STATUS_CHOICES = (
        ('PRESENT', _('Present')),
        ('LATE', _('Late')),
        ('ON_LEAVE', _('On Leave')),
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': _('Additional notes...')
        })
    )
    
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': _('Optional location information')
        })
    )


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form with email field."""
    
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'placeholder': _('your.email@example.com'),
            'class': 'form-control-lg'
        })
    )


class CustomSetPasswordForm(SetPasswordForm):
    """Custom password set form with styling."""
    
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'form-control-lg'
        }),
        strip=False,
    )
    
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'form-control-lg'
        }),
    )


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile information."""
    
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Date of Birth')
    )
    
    hire_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_('Hire Date')
    )
    
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        label=_('Profile Picture')
    )

    class Meta:
        model = Profile
        fields = [
            'phone_number',
            'address',
            'date_of_birth',
            'emergency_contact',
            'emergency_phone',
            'position',
            'hire_date',
            'profile_picture'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_date_of_birth(self):
        """Validate date of birth is not in the future."""
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.now().date():
            raise ValidationError(_("Date of birth cannot be in the future"))
        return dob

    def clean_hire_date(self):
        """Validate hire date is not in the future."""
        hire_date = self.cleaned_data.get('hire_date')
        if hire_date and hire_date > timezone.now().date():
            raise ValidationError(_("Hire date cannot be in the future"))
        return hire_date


class ReportGenerationForm(BaseForm):
    """Form for generating attendance reports."""
    
    report_type = forms.ChoiceField(
        choices=[
            ('DAILY', _('Daily')),
            ('WEEKLY', _('Weekly')),
            ('MONTHLY', _('Monthly')),
            ('CUSTOM', _('Custom Date Range')),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'onchange': 'updateDateFields()'
        }),
        initial='MONTHLY',
        label=_('Report Type')
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        label=_('Start Date')
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        required=False,
        label=_('End Date')
    )
    
    include_details = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_('Include detailed records')
    )

    def __init__(self, *args, **kwargs):
        """Initialize form with default date values."""
        super().__init__(*args, **kwargs)
        today = timezone.now().date()
        self.fields['start_date'].initial = today - datetime.timedelta(days=30)
        self.fields['end_date'].initial = today

    def clean(self):
        """Validate date range."""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date') or start_date
        
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError(_("Start date must be before end date"))
            
            if (end_date - start_date).days > 365:
                raise ValidationError(_("Date range cannot exceed one year"))
        
        return cleaned_data


class CompanyRegistrationStep1Form(forms.Form):
    """Step 1: Company Information"""
    company_name = forms.CharField(
        max_length=100,
        label="Company Name",
        widget=forms.TextInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Your company name',
            'required': True
        })
    )
    
    industry = forms.ChoiceField(
        choices=Organization.INDUSTRY_CHOICES,
        label="Industry",
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'required': True
        })
    )
    
    company_size = forms.ChoiceField(
        choices=Organization.SIZE_CHOICES,
        label="Company Size",
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'required': True
        })
    )
    
    address = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Company address',
            'required': True
        }),
        label="Address"
    )
    
    logo = forms.ImageField(
        required=False,
        label="Company Logo",
        widget=forms.FileInput(attrs={
            'class': 'sr-only',
            'accept': 'image/jpeg,image/jpg,image/png'
        })
    )
    
    def clean_company_name(self):
        company_name = self.cleaned_data.get('company_name', '').strip()
        if not company_name:
            raise ValidationError("Company name is required.")
        
        if len(company_name) < 2:
            raise ValidationError("Company name must be at least 2 characters long.")
        
        return company_name
    
    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo:
            # Validate file size (5MB limit)
            if logo.size > 5 * 1024 * 1024:
                raise ValidationError("Logo file size must be less than 5MB.")
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png']
            if logo.content_type not in allowed_types:
                raise ValidationError("Logo must be a JPEG or PNG image.")
        
        return logo

class CompanyRegistrationStep3Form(forms.Form):
    """Step 3: Admin User Creation"""
    first_name = forms.CharField(
        max_length=30,
        label="First Name",
        widget=forms.TextInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Admin first name',
            'required': True
        })
    )
    
    last_name = forms.CharField(
        max_length=30,
        label="Last Name",
        widget=forms.TextInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Admin last name',
            'required': True
        })
    )
    
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'admin@company.com',
            'required': True
        })
    )
    
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Create password',
            'required': True
        })
    )
    
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 py-2 px-3',
            'placeholder': 'Repeat password',
            'required': True
        })
    )
    
    terms = forms.BooleanField(
        required=True,
        label="I agree to the terms and conditions",
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        }),
        error_messages={
            'required': 'You must agree to the terms and conditions to continue.'
        }
    )
    
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError("Email is required.")
        
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError("Please enter a valid email address.")
        
        # Check if email already exists
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email is already registered.")
        
        return email
    
    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '').strip()
        if not first_name:
            raise ValidationError("First name is required.")
        
        if not re.match(r'^[a-zA-Z\s]+$', first_name):
            raise ValidationError("First name can only contain letters and spaces.")
        
        return first_name.title()
    
    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '').strip()
        if not last_name:
            raise ValidationError("Last name is required.")
        
        if not re.match(r'^[a-zA-Z\s]+$', last_name):
            raise ValidationError("Last name can only contain letters and spaces.")
        
        return last_name.title()
    
    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not password1:
            raise ValidationError("Password is required.")
        
        if len(password1) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        
        return password1
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError("Passwords don't match.")
        
        return cleaned_data

class JoinCompanyForm(UserCreationForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'hx-get': reverse_lazy('get_departments'),
            'hx-target': '#id_department',
            'hx-trigger': 'change'
        })
    )
    position = forms.ChoiceField(choices=User.POSITION_CHOICES)
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'organization', 'position', 'department']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize empty department queryset
        self.fields['department'].queryset = Department.objects.none()
        
        # If organization is in POST data, filter departments
        if 'organization' in self.data:
            try:
                org_id = int(self.data.get('organization'))
                self.fields['department'].queryset = Department.objects.filter(organization_id=org_id)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.organization:
            # If editing an existing user, show their organization's departments
            self.fields['department'].queryset = self.instance.organization.departments.all()