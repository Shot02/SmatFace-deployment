import base64
import csv
import json
import logging
import os
import pickle
import tempfile
import random
import secrets
from datetime import datetime, timedelta

import cv2
import numpy as np
import face_recognition
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.conf import settings

from .forms import (
    EmailLoginForm,
    CustomSignupForm,
    FaceRegistrationForm,
    AttendanceForm,
    UserProfileForm,
    ReportGenerationForm,
    CompanyRegistrationStep1Form,
    CompanyRegistrationStep3Form
)
from .models import User, Attendance, FaceProfile, AttendanceReport, Profile, AIMessage, AIFeedback, Organization, Department
from .utils import face_recognizer
from .ai_utils import get_ai_message, handle_ai_feedback

logger = logging.getLogger(__name__)

# ========== UTILITY FUNCTIONS ==========
def get_client_ip(request):
    """Extract client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

def determine_attendance_status(current_time):
    """Determine if attendance is marked as present or late"""
    cutoff_time = datetime.strptime('09:30', '%H:%M').time()
    return 'PRESENT' if current_time <= cutoff_time else 'LATE'

def verify_user_face(user, frame):
    """Verify user's face against stored face encoding with enhanced security"""
    try:
        if not hasattr(user, 'face_profile') or not user.face_profile.face_encoding:
            return False
            
        # Process the frame to find faces
        result = face_recognizer.process_frame(frame)
        if not result.get('is_valid', False):
            return False
            
        # Check if multiple faces are detected (potential spoofing attempt)
        if result.get('face_count', 0) > 1:
            logger.warning(f"Multiple faces detected during verification for user {user.id}")
            return False
            
        # Get the face embedding
        embedding = face_recognizer.get_face_embedding(frame, result['face_location'])
        if embedding is None:
            return False
            
        # Compare with stored encoding
        stored_encoding = pickle.loads(user.face_profile.face_encoding)
        similarity = np.dot(embedding, stored_encoding)
        
        # Use a higher threshold for stricter matching
        threshold = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.8)
        
        # Update last used timestamp
        if similarity > threshold:
            user.face_profile.last_used = timezone.now()
            user.face_profile.save(update_fields=['last_used'])
            return True
            
        return False
    except Exception as e:
        logger.error(f"Face verification error: {str(e)}")
        return False

# ========== CORE VIEWS ==========
def home_view(request):
    """Home page view"""
    context = {
        'has_attendance_today': False,
        'attendance_today': None
    }
    
    if request.user.is_authenticated:
        today = timezone.now().date()
        attendance_today = Attendance.objects.filter(user=request.user, date=today).first()
        context.update({
            'has_attendance_today': attendance_today is not None,
            'attendance_today': attendance_today
        })
    
    return render(request, 'attendance/index.html', context)

@login_required
def dashboard_view(request):
    """Main dashboard view with attendance statistics"""
    today = timezone.now().date()
    start_date = today - timedelta(days=30)
    
    user_attendance = Attendance.objects.filter(
        user=request.user,
        date__range=[start_date, today]
    ).order_by('-date')
    
    today_attendance = user_attendance.filter(date=today).first()
    present_count = user_attendance.filter(status='PRESENT').count()
    late_count = user_attendance.filter(status='LATE').count()
    attendance_rate = (present_count / 30) * 100 if present_count > 0 else 0
    
    context = {
        'today_attendance': today_attendance,
        'attendance_rate': round(attendance_rate, 1),
        'present_count': present_count,
        'late_count': late_count,
        'recent_activity': user_attendance[:5],
        'monthly_data': json.dumps(list(user_attendance
            .values('date__month')
            .annotate(
                present=Count('id', filter=Q(status='PRESENT')),
                late=Count('id', filter=Q(status='LATE'))
            )
            .order_by('date__month'))),
        'is_admin': request.user.is_staff or request.user.position in ['ADMIN', 'DIRECTOR']
    }
    
    if context['is_admin']:
        # Add admin-specific context
        organization = request.user.organization
        if organization:
            context.update({
                'leaderboard': User.objects
                    .filter(organization=organization)
                    .annotate(attendance_count=Count('attendances', filter=Q(attendances__status='PRESENT')))
                    .order_by('-attendance_count')[:5],
                'department_stats': Department.objects
                    .filter(organization=organization)
                    .annotate(
                        staff_count=Count('user'),
                        present_count=Count('user__attendances', filter=Q(user__attendances__status='PRESENT')))
            })
    
    return render(request, 'attendance/dashboard.html', context)

# ========== AUTHENTICATION VIEWS ==========
@require_http_methods(["GET", "POST"])
def login_view(request):
    """Handle user login with email/password"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    form = EmailLoginForm(request, data=request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            user.last_login_ip = get_client_ip(request)
            user.save(update_fields=['last_login_ip'])
            messages.success(request, "Logged in successfully!")
            return redirect(request.GET.get('next', 'dashboard'))
        
        messages.error(request, "Invalid email or password")
    
    return render(request, 'auth/login.html', {'form': form})

@require_http_methods(["GET"])
def face_login_view(request):
    """Face login page view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    return render(request, 'auth/face_login.html')

@csrf_exempt
def verify_face_login(request):
    """API endpoint for face login verification with enhanced security"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    if 'face_image' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No image provided'}, status=400)

    try:
        # Process the image
        img_data = request.FILES['face_image'].read()
        frame = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        
        if frame is None:
            return JsonResponse({'success': False, 'error': 'Invalid image format'}, status=400)
        
        # Process the frame to find faces
        result = face_recognizer.process_frame(frame)
        if not result.get('is_valid', False):
            return JsonResponse({'success': False, 'error': result.get('error', 'Face detection failed')}, status=400)
        
        # Check if multiple faces are detected (potential spoofing attempt)
        if result.get('face_count', 0) > 1:
            return JsonResponse({'success': False, 'error': 'Multiple faces detected. Please ensure only your face is in the frame'}, status=400)
            
        # Identify the user
        user_id = face_recognizer.identify_user(frame, result['face_location'])
        if not user_id:
            return JsonResponse({'success': False, 'error': 'Face not recognized. Please register or use email login.'}, status=400)
            
        # Get the user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=400)
            
        # Update last used timestamp
        if hasattr(user, 'face_profile'):
            user.face_profile.last_used = timezone.now()
            user.face_profile.save(update_fields=['last_used'])
            
        # Log the user in
        login(request, user)
        user.last_login_ip = get_client_ip(request)
        user.save(update_fields=['last_login_ip'])
        
        # Check if we should mark attendance
        attendance_marked = False
        message = ""
        today = timezone.now().date()
        now = timezone.now()
        
        # Mark attendance if not already marked
        existing = Attendance.objects.filter(user=user, date=today).first()
        if not existing:
            status = determine_attendance_status(now.time())
            Attendance.objects.create(
                user=user,
                date=today,
                time_in=now.time(),
                status=status,
                method='FACE'
            )
            attendance_marked = True
            message = get_ai_message(user, 'mark_in')
            
            # Store the action in session
            if hasattr(request, 'session'):
                request.session['last_attendance_action'] = 'mark_in'
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('dashboard'),
            'attendance_marked': attendance_marked,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Face login error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred. Please try again.'}, status=500)


def signup_view(request):
    """User signup view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    form = CustomSignupForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                
                # Set organization and department
                organization = form.cleaned_data.get('organization')
                user.organization = organization
                
                # Set department if provided
                department = form.cleaned_data.get('department')
                if department:
                    user.department = department
                    
                # Set position
                user.position = form.cleaned_data.get('position', 'STAFF')
                
                # Save user
                user.save()
                
                # Create profile
                Profile.objects.create(user=user)
                
                # Log user in
                login(request, user)
                messages.success(request, "Account created successfully! Please register your face.")
                return redirect('register_face')
                
        except Exception as e:
            logger.error(f"Error during signup: {str(e)}")
            messages.error(request, "An error occurred during registration. Please try again.")
            
    return render(request, 'auth/signup.html', {'form': form})

# ========== PROFILE MANAGEMENT ==========
@login_required
def profile_view(request):
    """View user profile"""
    return render(request, 'attendance/profile.html', {
        'is_admin': request.user.is_staff or request.user.position in ['ADMIN', 'DIRECTOR'],
        'has_face_profile': hasattr(request.user, 'face_profile')
    })

@login_required
def profile_update_view(request):
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)
        
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=profile)
    
    # Get departments for the user's organization
    departments = []
    if request.user.organization:
        departments = Department.objects.filter(organization=request.user.organization)
    
    if request.method == 'POST':
        if form.is_valid():
            # Save profile form
            form.save()
            
            # Update department if provided
            department_id = request.POST.get('department')
            if department_id:
                try:
                    department = Department.objects.get(id=department_id, organization=request.user.organization)
                    request.user.department = department
                    request.user.save(update_fields=['department'])
                except Department.DoesNotExist:
                    messages.error(request, "Selected department not found.")
                    
            messages.success(request, "Your profile has been updated successfully!")
            return redirect('profile')
        
    return render(request, 'attendance/profile_update.html', {
        'form': form,
        'departments': departments,
        'current_department': request.user.department
    })

# ========== FACE REGISTRATION ==========
@login_required
def register_face_view(request):
    """Face registration page view"""
    if hasattr(request.user, 'face_profile'):
        messages.info(request, "You have already registered your face.")
        return redirect('dashboard')
        
    return render(request, 'attendance/register_face.html')

@login_required
@csrf_exempt
def register_face_api(request):
    """API endpoint for face registration with enhanced security"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    if 'image' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No image provided'}, status=400)
    
    try:
        if hasattr(request.user, 'face_profile'):
            return JsonResponse({'success': False, 'error': 'Face already registered'}, status=400)
        
        img_data = request.FILES['image'].read()
        if not img_data:
            return JsonResponse({'success': False, 'error': 'Empty image data'}, status=400)
            
        frame = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return JsonResponse({'success': False, 'error': 'Invalid image format'}, status=400)
        
        result = face_recognizer.process_frame(frame)
        if not result.get('is_valid', False):
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Face detection failed')
            }, status=400)
        
        # Check if multiple faces are detected
        if result.get('face_count', 0) > 1:
            return JsonResponse({
                'success': False,
                'error': 'Multiple faces detected. Please ensure only your face is in the frame'
            }, status=400)
        
        embedding = face_recognizer.get_face_embedding(frame, result['face_location'])
        if embedding is None:
            return JsonResponse({'success': False, 'error': 'Could not extract face features'}, status=400)
        
        face_profile = FaceProfile(user=request.user)
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        face_profile.image.save(f'face_{request.user.id}.jpg', ContentFile(buffer.tobytes()))
        face_profile.face_encoding = pickle.dumps(embedding)
        face_profile.save()
        face_recognizer.load_known_faces()
        
        return JsonResponse({'success': True, 'message': 'Face registered successfully'})
        
    except Exception as e:
        logger.error(f"Face registration failed: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

# ========== ATTENDANCE MARKING ==========

@login_required
def process_attendance(request):
    """Process the actual attendance marking after face verification"""
    if request.method == 'POST':
        action = request.POST.get('action', 'mark_in')
        today = timezone.now().date()
        current_time = timezone.now().time()
        
        if action == 'mark_out':
            # Get today's attendance record
            today_attendance = Attendance.objects.filter(user=request.user, date=today).first()
            
            if not today_attendance:
                messages.error(request, "No mark-in record found for today.")
                return redirect('dashboard')
                
            if today_attendance.time_out:
                messages.warning(request, "You have already marked out for today.")
                return redirect('dashboard')
            
            # Update the attendance record with mark out time
            today_attendance.time_out = current_time
            today_attendance.save()
            
            # Get AI message for mark out
            message = get_ai_message(request.user, 'mark_out')
            
            messages.success(request, f"Successfully marked out at {current_time.strftime('%I:%M %p')}. {message}")
            return redirect('dashboard')
            
        elif action == 'mark_in':
            # Check if already marked in today
            today_attendance = Attendance.objects.filter(user=request.user, date=today).first()
            
            if today_attendance and not today_attendance.time_out:
                messages.warning(request, "You have already marked in today.")
                return redirect('dashboard')
            elif today_attendance and today_attendance.time_out:
                messages.warning(request, "You have already completed attendance for today.")
                return redirect('dashboard')
            
            # Create new attendance record
            status = determine_attendance_status(current_time)
            Attendance.objects.create(
                user=request.user,
                date=today,
                time_in=current_time,
                status=status,
                method='FACE'
            )
            
            # Get AI message for mark in
            message = get_ai_message(request.user, 'mark_in')
            
            messages.success(request, f"Successfully marked in at {current_time.strftime('%I:%M %p')}. {message}")
            return redirect('dashboard')
    
    return redirect('dashboard')


# 2. Update your existing mark_attendance function (add the action parameter):

@login_required
def mark_attendance(request):
    """Attendance marking view with restrictions"""
    action = request.GET.get('action', 'mark_in')
    today = timezone.now().date()
    
    # Check if user has already marked attendance today
    today_attendance = Attendance.objects.filter(user=request.user, date=today).first()
    
    # Handle mark out scenario
    if action == 'mark_out':
        if not today_attendance:
            messages.warning(request, "You need to mark in before you can mark out.")
            return redirect('dashboard')
            
        if today_attendance.time_out:
            messages.warning(request, "You have already marked out for today. You can mark in again tomorrow.")
            return redirect('dashboard')
            
        return render(request, 'attendance/mark.html', {
            'is_marking_in': False,
            'today_attendance': today_attendance,
            'action': 'mark_out'  # Add this line
        })
    
    # Handle mark in scenario
    if today_attendance:
        if today_attendance.time_out:
            # User has already completed a full attendance cycle today
            messages.warning(request, "You have already completed your attendance for today. Please come back tomorrow.")
            return redirect('dashboard')
        else:
            # User has marked in but not out yet
            messages.info(request, "You have already marked in today. Please mark out when leaving.")
            return redirect('dashboard')
    
    # If we get here, it's a valid mark in request
    return render(request, 'attendance/mark.html', {
        'is_marking_in': True,
        'today_attendance': None,
        'action': 'mark_in' 
    })


@csrf_exempt
@login_required
def verify_face_attendance(request):
    """API endpoint for face verification and attendance marking with enhanced security"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    if 'face_image' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No image provided'}, status=400)

    try:
        # Process the image
        img_data = request.FILES['face_image'].read()
        frame = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        
        if frame is None:
            return JsonResponse({'success': False, 'error': 'Invalid image format'}, status=400)
        
        # Process the frame to find faces
        result = face_recognizer.process_frame(frame)
        if not result.get('is_valid', False):
            return JsonResponse({'success': False, 'error': result.get('error', 'Face detection failed')}, status=400)
        
        # Check if multiple faces are detected (potential spoofing attempt)
        if result.get('face_count', 0) > 1:
            return JsonResponse({'success': False, 'error': 'Multiple faces detected. Please ensure only your face is in the frame'}, status=400)
        
        # Verify face
        if not verify_user_face(request.user, frame):
            return JsonResponse({'success': False, 'error': 'Face verification failed. Please try again.'}, status=400)

        # Process attendance
        today = timezone.now().date()
        now = timezone.now()
        action = request.POST.get('action', 'mark_in')
        
        if action == 'mark_in':
            # Check if already marked in
            existing = Attendance.objects.filter(user=request.user, date=today).first()
            if existing:
                if existing.time_out:
                    return JsonResponse({
                        'success': False, 
                        'error': 'You have already completed your attendance for today. Please come back tomorrow.'
                    }, status=400)
                else:
                    return JsonResponse({
                        'success': False, 
                        'error': 'You have already marked in today. Please mark out when leaving.'
                    }, status=400)
                
            # Create new attendance record
            status = determine_attendance_status(now.time())
            attendance = Attendance.objects.create(
                user=request.user,
                date=today,
                time_in=now.time(),
                status=status,
                method='FACE'
            )
            
            # Store the action in session
            if hasattr(request, 'session'):
                request.session['last_attendance_action'] = 'mark_in'
                
            message = get_ai_message(request.user, 'mark_in')
            
            # Prepare attendance data for response
            attendance_data = {
                'date': today.strftime('%Y-%m-%d'),
                'time_in': now.strftime('%H:%M:%S'),
                'status': attendance.status
            }
            
        else:  # mark out
            try:
                attendance = Attendance.objects.get(user=request.user, date=today)
                if attendance.time_out:
                    return JsonResponse({
                        'success': False, 
                        'error': 'You have already marked out for today. You can mark in again tomorrow.'
                    }, status=400)
                    
                attendance.time_out = now.time()
                attendance.save()
                
                # Store the action in session
                if hasattr(request, 'session'):
                    request.session['last_attendance_action'] = 'mark_out'
                    
                message = get_ai_message(request.user, 'mark_out')
                
                # Calculate duration
                time_in_dt = datetime.combine(today, attendance.time_in)
                time_out_dt = datetime.combine(today, attendance.time_out)
                duration = time_out_dt - time_in_dt
                hours = int(duration.total_seconds() // 3600)
                minutes = int((duration.total_seconds() % 3600) // 60)
                
                # Prepare attendance data for response
                attendance_data = {
                    'date': today.strftime('%Y-%m-%d'),
                    'time_in': attendance.time_in.strftime('%H:%M:%S'),
                    'time_out': attendance.time_out.strftime('%H:%M:%S'),
                    'duration': f"{hours}h {minutes}m",
                    'status': attendance.status
                }
                
            except Attendance.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'No attendance record found for today. Please mark in first.'
                }, status=400)
        
        return JsonResponse({
            'success': True,
            'message': message,
            'attendance_data': attendance_data,
            'redirect_url': reverse('dashboard')  # Add redirect URL
        })

    except Exception as e:
        logger.error(f"Attendance verification error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred. Please try again.'}, status=500)

# ========== AI INTEGRATION ==========
@login_required
def get_ai_message_view(request):
    """API endpoint for AI-generated messages"""
    try:
        context = request.GET.get('context', 'daily_boost')
        message = get_ai_message(request.user, context)
        return JsonResponse({'message': message})
    except Exception as e:
        logger.error(f"AI message error: {str(e)}")
        return JsonResponse({'message': "Stay productive today!"})

@login_required
@csrf_exempt
def ai_feedback_view(request):
    """Handle feedback on AI messages"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    try:
        data = json.loads(request.body)
        is_positive = data.get('is_positive', True)
        message = data.get('message', '')
        
        handle_ai_feedback(request.user, is_positive, message)
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"AI feedback error: {str(e)}")
        return JsonResponse({'success': False}, status=400)

# ========== COMPANY REGISTRATION ==========
@require_http_methods(["GET", "POST"])
@csrf_protect
def register_company(request):
    """Multi-step company registration view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Get registration data from session
    registration_data = request.session.get('registration_data', {})
    
    # Handle step navigation via GET parameter
    if request.method == 'GET' and 'step' in request.GET:
        try:
            requested_step = int(request.GET['step'])
            if 1 <= requested_step <= 3:
                registration_data['step'] = requested_step
                request.session['registration_data'] = registration_data
        except (ValueError, TypeError):
            pass
    
    # Get current step (default to 1)
    current_step = registration_data.get('step', 1)

    # Process form submission
    if request.method == 'POST':
        step = int(request.POST.get('step', 1))
        
        # Step 1: Company Information
        if step == 1:
            form = CompanyRegistrationStep1Form(request.POST, request.FILES)
            
            if form.is_valid():
                # Store company data in session
                registration_data.update({
                    'step': 2,
                    'company_name': form.cleaned_data['company_name'],
                    'industry': form.cleaned_data['industry'],
                    'company_size': form.cleaned_data['company_size'],
                    'address': form.cleaned_data['address'],
                })
                
                # Handle logo upload
                if 'logo' in request.FILES:
                    logo = request.FILES['logo']
                    temp_filename = f"temp_logo_{request.session.session_key}_{logo.name}"
                    temp_path = default_storage.save(f"temp/{temp_filename}", ContentFile(logo.read()))
                    registration_data['temp_logo_path'] = temp_path
                
                request.session['registration_data'] = registration_data
                return redirect('register_company')
            else:
                # Return to step 1 with form errors
                return render(request, 'attendance/register_company.html', {
                    'step': 1,
                    'form': form,
                    'progress_steps': _get_progress_steps(1),
                    'progress_percentage': _get_progress_percentage(1)
                })

        # Step 2: Departments
        elif step == 2:
            try:
                department_count = int(request.POST.get('department_count', 1))
                
                if not 1 <= department_count <= 9:
                    raise ValidationError("Department count must be between 1 and 9")
                
                departments = []
                for i in range(1, department_count + 1):
                    dept_name = request.POST.get(f'department_{i}', '').strip()
                    if dept_name:
                        departments.append(dept_name)
                    else:
                        raise ValidationError(f"Department {i} name is required")
                
                if not departments:
                    raise ValidationError("Please add at least one department")
                
                # Check for duplicate department names
                if len(departments) != len(set(departments)):
                    raise ValidationError("Department names must be unique")
                
                registration_data.update({
                    'step': 3,
                    'departments': departments,
                    'department_count': department_count
                })
                request.session['registration_data'] = registration_data
                return redirect('register_company')
            
            except (ValueError, ValidationError) as e:
                # Return to step 2 with error
                return render(request, 'attendance/register_company.html', {
                    'step': 2,
                    'error': str(e),
                    'department_count': registration_data.get('department_count', 1),
                    'department_range': range(1, 10),
                    'department_fields': _get_department_fields(registration_data),
                    'progress_steps': _get_progress_steps(2),
                    'progress_percentage': _get_progress_percentage(2)
                })

        # Step 3: Admin User Creation
        elif step == 3:
            form = CompanyRegistrationStep3Form(request.POST)
            
            if form.is_valid():
                try:
                    with transaction.atomic():
                        # Create Organization
                        org = Organization.objects.create(
                            name=registration_data['company_name'],
                            industry=registration_data['industry'],
                            size=registration_data['company_size'],
                            address=registration_data['address']
                        )
                        
                        # Handle logo if uploaded
                        if registration_data.get('temp_logo_path'):
                            temp_path = registration_data['temp_logo_path']
                            if default_storage.exists(temp_path):
                                # Move from temp to permanent location
                                logo_filename = f"org_{org.id}_logo.{temp_path.split('.')[-1]}"
                                permanent_path = f"logos/{logo_filename}"
                                
                                # Copy file content
                                with default_storage.open(temp_path, 'rb') as temp_file:
                                    permanent_file = default_storage.save(permanent_path, ContentFile(temp_file.read()))
                                
                                org.logo = permanent_file
                                org.save()
                                
                                # Clean up temp file
                                default_storage.delete(temp_path)
                        
                        # Create Departments
                        created_departments = []
                        for dept_name in registration_data['departments']:
                            dept = Department.objects.create(
                                organization=org,
                                name=dept_name,
                                code=dept_name[:3].upper()
                            )
                            created_departments.append(dept)
                        
                        # Create Admin User
                        user = User.objects.create_user(
                            email=form.cleaned_data['email'],
                            password=form.cleaned_data['password1'],
                            first_name=form.cleaned_data['first_name'],
                            last_name=form.cleaned_data['last_name'],
                            organization=org,
                            position='ADMIN',
                            is_staff=True,
                            is_verified=True
                        )
                        
                        # Create profile
                        Profile.objects.create(user=user, position='Administrator')
                        
                        # Clear session data
                        if 'registration_data' in request.session:
                            del request.session['registration_data']
                        
                        # Log in the user
                        login(request, user)
                        
                        # Redirect to success page
                        return redirect('registration_success')
                
                except Exception as e:
                    logger.error(f"Registration failed: {str(e)}")
                    return render(request, 'attendance/register_company.html', {
                        'step': 3,
                        'form': form,
                        'error': f'Registration failed: {str(e)}',
                        'progress_steps': _get_progress_steps(3),
                        'progress_percentage': _get_progress_percentage(3)
                    })
            else:
                # Return to step 3 with form errors
                return render(request, 'attendance/register_company.html', {
                    'step': 3,
                    'form': form,
                    'progress_steps': _get_progress_steps(3),
                    'progress_percentage': _get_progress_percentage(3)
                })

    # GET request - show appropriate step
    if current_step == 1:
        form = CompanyRegistrationStep1Form(initial={
            'company_name': registration_data.get('company_name', ''),
            'industry': registration_data.get('industry', ''),
            'company_size': registration_data.get('company_size', ''),
            'address': registration_data.get('address', ''),
        })
        return render(request, 'attendance/register_company.html', {
            'step': 1,
            'form': form,
            'progress_steps': _get_progress_steps(1),
            'progress_percentage': _get_progress_percentage(1)
        })
    
    elif current_step == 2:
        return render(request, 'attendance/register_company.html', {
            'step': 2,
            'department_count': registration_data.get('department_count', 1),
            'department_range': range(1, 10),
            'department_fields': _get_department_fields(registration_data),
            'progress_steps': _get_progress_steps(2),
            'progress_percentage': _get_progress_percentage(2)
        })
    
    else:  # Step 3
        form = CompanyRegistrationStep3Form()
        return render(request, 'attendance/register_company.html', {
            'step': 3,
            'form': form,
            'progress_steps': _get_progress_steps(3),
            'progress_percentage': _get_progress_percentage(3)
        })

def _get_progress_steps(current_step):
    """Helper function to get progress steps"""
    steps = [
        {'number': 1, 'title': 'Company Info'},
        {'number': 2, 'title': 'Departments'},
        {'number': 3, 'title': 'Admin Setup'},
    ]
    
    for step in steps:
        step['current'] = step['number'] == current_step
    
    return steps

def _get_progress_percentage(current_step):
    """Helper function to calculate progress percentage"""
    total_steps = 3
    return ((current_step - 1) / (total_steps - 1)) * 100 if total_steps > 1 else 0

def _get_department_fields(registration_data):
    """Helper function to get department fields"""
    department_count = registration_data.get('department_count', 1)
    existing_departments = registration_data.get('departments', [])
    
    return [
        {
            'name': f'department_{i+1}',
            'label': f'Department {i+1} Name',
            'value': existing_departments[i] if i < len(existing_departments) else ''
        }
        for i in range(department_count)
    ]

def get_department_fields(request):
    """AJAX endpoint for dynamic department fields"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        count = int(request.POST.get('department_count', 0))
        if not 1 <= count <= 9:
            return JsonResponse({'error': 'Invalid department count'}, status=400)
        
        registration_data = request.session.get('registration_data', {})
        existing_departments = registration_data.get('departments', [])
        
        fields = []
        for i in range(count):
            fields.append({
                'name': f'department_{i+1}',
                'label': f'Department {i+1} Name',
                'value': existing_departments[i] if i < len(existing_departments) else ''
            })
        
        html = render_to_string('attendance/dept_field.html', {'fields': fields})
        return HttpResponse(html)
    
    except Exception as e:
        logger.error(f"Error in get_department_fields: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)

@require_GET
def get_departments(request):
    org_id = request.GET.get('organization_id')
    if not org_id:
        return JsonResponse({'departments': []})
    
    departments = Department.objects.filter(organization_id=org_id).values('id', 'name')
    return JsonResponse({'departments': list(departments)})

@csrf_protect
def registration_success(request):
    """Display registration success page"""
    if not request.user.is_authenticated:
        return redirect('register_company')
        
    return render(request, 'attendance/registration_success.html', {
        'company_name': request.user.organization.name if request.user.organization else 'your company'
    })

# ========== ADMIN DASHBOARD ==========
@login_required
def admin_dashboard_view(request):
    """Admin dashboard view with organization management"""
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to access the admin dashboard.")
        return redirect('dashboard')
    
    organization = request.user.organization
    today = timezone.now().date()
    
    # Get all staff in the organization
    staff_list = User.objects.filter(organization=organization).order_by('last_name', 'first_name')
    
    # Get department statistics
    departments = Department.objects.filter(organization=organization)
    department_stats = []
    
    for dept in departments:
        staff_count = User.objects.filter(department=dept).count()
        present_today = Attendance.objects.filter(
            user__department=dept,
            date=today
        ).count()
        
        attendance_rate = (present_today / staff_count * 100) if staff_count > 0 else 0
        
        department_stats.append({
            'name': dept.name,
            'staff_count': staff_count,
            'present_today': present_today,
            'attendance_rate': round(attendance_rate)
        })
    
    # Calculate overall statistics
    user_count = staff_list.count()
    department_count = departments.count()
    today_attendance_count = Attendance.objects.filter(
        user__organization=organization,
        date=today
    ).count()
    
    today_attendance_percentage = round((today_attendance_count / user_count * 100)) if user_count > 0 else 0
    
    context = {
        'staff_list': staff_list,
        'department_stats': department_stats,
        'user_count': user_count,
        'department_count': department_count,
        'today_attendance_count': today_attendance_count,
        'today_attendance_percentage': today_attendance_percentage
    }
    
    return render(request, 'attendance/admin_dashboard.html', context)

# ========== REPORTS ==========
@login_required
def reports_view(request):
    """Generate and view attendance reports"""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    form = ReportGenerationForm(request.POST or None, initial={
        'start_date': start_date,
        'end_date': end_date,
        'report_type': 'MONTHLY'
    })
    
    attendance_records = None
    if request.method == 'POST' and form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        
        if form.cleaned_data['report_type'] == 'DAILY':
            end_date = start_date
        elif form.cleaned_data['report_type'] == 'WEEKLY':
            end_date = start_date + timedelta(days=6)
        
        attendance_records = Attendance.objects.filter(
            user=request.user,
            date__range=[start_date, end_date]
        ).order_by('date')
    
    return render(request, 'attendance/reports.html', {
        'form': form,
        'attendance_records': attendance_records,
        'generated_report': attendance_records is not None
    })

@login_required
def download_report(request):
    """Download attendance report as CSV"""
    if not all(k in request.GET for k in ['start_date', 'end_date', 'report_type']):
        return HttpResponse(_("Invalid report parameters"), status=400)
    
    try:
        start_date = datetime.strptime(request.GET['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.GET['end_date'], '%Y-%m-%d').date()
        
        records = Attendance.objects.filter(
            user=request.user,
            date__range=[start_date, end_date]
        ).order_by('date')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_report_{start_date}_to_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([_('Date'), _('Status'), _('Time In'), _('Time Out'), _('Duration'), _('Method')])
        
        for record in records:
            writer.writerow([
                record.date,
                record.get_status_display(),
                record.time_in.strftime('%H:%M:%S') if record.time_in else '',
                record.time_out.strftime('%H:%M:%S') if record.time_out else '',
                record.get_duration_display(),
                record.get_method_display()
            ])
        
        AttendanceReport.objects.create(
            user=request.user,
            report_type=request.GET['report_type'],
            start_date=start_date,
            end_date=end_date,
            record_count=records.count()
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Report generation error: {str(e)}")
        messages.error(request, _("Error generating report"))
        return redirect('reports')

# ========== ADMIN FUNCTIONS ==========
@login_required
def delete_user(request, user_id):
    """Delete a user (admin only)"""
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('dashboard')
        
    try:
        user_to_delete = get_object_or_404(User, id=user_id, organization=request.user.organization)
        
        # Don't allow deleting yourself
        if user_to_delete == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('admin_dashboard')
            
        # Delete the user
        user_name = user_to_delete.get_full_name()
        user_to_delete.delete()
        messages.success(request, f"User {user_name} has been deleted successfully.")
        
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        messages.error(request, "An error occurred while deleting the user.")
        
    return redirect('admin_dashboard')

@login_required
def clear_company_data(request):
    """Clear all company data (admin only)"""
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('dashboard')
        
    if request.method != 'POST':
        return render(request, 'attendance/confirm_clear_data.html')
        
    try:
        organization = request.user.organization
        
        # Verify confirmation
        confirmation = request.POST.get('confirmation')
        if confirmation != organization.name:
            messages.error(request, "Confirmation text doesn't match your company name.")
            return render(request, 'attendance/confirm_clear_data.html')
            
        with transaction.atomic():
            # Delete all attendance records
            Attendance.objects.filter(user__organization=organization).delete()
            
            # Delete all face profiles
            for profile in FaceProfile.objects.filter(user__organization=organization):
                if profile.image:
                    # Check if the file exists before trying to delete it
                    if default_storage.exists(profile.image.name):
                        default_storage.delete(profile.image.name)
                profile.delete()
            
            # Delete all reports
            AttendanceReport.objects.filter(user__organization=organization).delete()
            
            # Delete all AI feedback
            AIFeedback.objects.filter(user__organization=organization).delete()
            
            # Reset face recognizer
            face_recognizer.load_known_faces()
            
        messages.success(request, "All company data has been cleared successfully.")
        
    except Exception as e:
        logger.error(f"Error clearing company data: {str(e)}")
        messages.error(request, "An error occurred while clearing company data.")
        
    return redirect('admin_dashboard')

# ========== FACE DETECTION API ==========
@csrf_exempt
def face_detection_api(request):
    """API endpoint for face detection"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image provided'}, status=400)
    
    try:
        img_data = request.FILES['image'].read()
        if not img_data:
            return JsonResponse({'error': 'Empty image data'}, status=400)
            
        frame = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return JsonResponse({'error': 'Invalid image format'}, status=400)
        
        result = face_recognizer.process_frame(frame)
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"API error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Processing failed'}, status=500)

# ========== ADMIN FUNCTIONS ==========
@login_required
def delete_user(request, user_id):
    """Delete a user (admin only)"""
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('dashboard')
        
    try:
        user_to_delete = get_object_or_404(User, id=user_id, organization=request.user.organization)
        
        # Don't allow deleting yourself
        if user_to_delete == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('admin_dashboard')
            
        # Delete the user
        user_name = user_to_delete.get_full_name()
        user_to_delete.delete()
        messages.success(request, f"User {user_name} has been deleted successfully.")
        
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        messages.error(request, "An error occurred while deleting the user.")
        
    return redirect('admin_dashboard')

@login_required
def clear_company_data(request):
    """Clear all company data (admin only)"""
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('dashboard')
        
    if request.method != 'POST':
        return render(request, 'attendance/confirm_clear_data.html')
        
    try:
        organization = request.user.organization
        
        # Verify confirmation
        confirmation = request.POST.get('confirmation')
        if confirmation != organization.name:
            messages.error(request, "Confirmation text doesn't match your company name.")
            return render(request, 'attendance/confirm_clear_data.html')
            
        with transaction.atomic():
            # Delete all attendance records
            Attendance.objects.filter(user__organization=organization).delete()
            
            # Delete all face profiles
            for profile in FaceProfile.objects.filter(user__organization=organization):
                if profile.image:
                    default_storage.delete(profile.image.path)
                profile.delete()
            
            # Delete all reports
            AttendanceReport.objects.filter(user__organization=organization).delete()
            
            # Delete all AI feedback
            AIFeedback.objects.filter(user__organization=organization).delete()
            
            # Reset face recognizer
            face_recognizer.load_known_faces()
            
        messages.success(request, "All company data has been cleared successfully.")
        
    except Exception as e:
        logger.error(f"Error clearing company data: {str(e)}")
        messages.error(request, "An error occurred while clearing company data.")
        
    return redirect('admin_dashboard')

@login_required
def send_invitation(request):
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to send invitations.")
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            validate_email(email)
            
            # Create invitation link
            invitation_token = secrets.token_urlsafe(32)
            cache.set(f'invitation_{email}', invitation_token, timeout=86400)  # 24 hours
            
            # Send email
            subject = f"Invitation to join {request.user.organization.name}"
            invitation_link = request.build_absolute_uri(
                reverse('accept_invitation', kwargs={'token': invitation_token}))
            
            message = render_to_string('attendance/email/invitation_email.txt', {
                'organization': request.user.organization.name,
                'inviter': request.user.get_full_name(),
                'invitation_link': invitation_link,
            })
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            
            messages.success(request, f"Invitation sent to {email}")
            return redirect('admin_dashboard')
            
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
    
    return render(request, 'attendance/send_invitation.html')

def accept_invitation(request, token):
    # Validate token from cache
    email = None
    for key in cache.iter_keys('invitation_*'):
        if cache.get(key) == token:
            email = key.replace('invitation_', '')
            break

    if not email:
        messages.error(request, "Invalid or expired invitation link.")
        return redirect('login')

    # Do something like creating an account for email
    return render(request, 'attendance/accept_invitation.html', {'email': email})

@login_required
def manage_departments(request):
    if not request.user.is_admin:
        messages.error(request, "You don't have permission to manage departments.")
        return redirect('dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            name = request.POST.get('name')
            if name:
                Department.objects.create(
                    organization=request.user.organization,
                    name=name,
                    code=name[:3].upper()
                )
                messages.success(request, f"Department '{name}' added successfully.")
                
        elif action == 'delete':
            dept_id = request.POST.get('dept_id')
            try:
                dept = Department.objects.get(id=dept_id, organization=request.user.organization)
                dept.delete()
                messages.success(request, "Department deleted successfully.")
            except Department.DoesNotExist:
                messages.error(request, "Department not found.")
                
        elif action == 'edit':
            dept_id = request.POST.get('dept_id')
            new_name = request.POST.get('new_name')
            try:
                dept = Department.objects.get(id=dept_id, organization=request.user.organization)
                dept.name = new_name
                dept.code = new_name[:3].upper()
                dept.save()
                messages.success(request, "Department updated successfully.")
            except Department.DoesNotExist:
                messages.error(request, "Department not found.")
    
    departments = Department.objects.filter(organization=request.user.organization)
    return render(request, 'attendance/manage_departments.html', {'departments': departments})


def is_admin_user(user):
    return user.is_authenticated and user.position == 'ADMIN'

@login_required
@user_passes_test(is_admin_user)
def view_user_profile(request, user_id):
    """View user profile (admin only)"""
    profile_user = get_object_or_404(User, id=user_id, organization=request.user.organization)
    
    # Get attendance statistics
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    attendance_records = Attendance.objects.filter(
        user=profile_user,
        date__gte=thirty_days_ago
    )
    
    present_count = attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
    late_count = attendance_records.filter(status='LATE').count()
    attendance_rate = round((present_count / 30) * 100, 1) if present_count > 0 else 0
    
    # Get today's attendance
    today_attendance = Attendance.objects.filter(
        user=profile_user,
        date=timezone.now().date()
    ).first()
    
    # Get recent attendance (last 10 days)
    recent_attendance = Attendance.objects.filter(
        user=profile_user
    ).order_by('-date')[:10]
    
    # Calculate duration for each record
    for record in recent_attendance:
        if record.time_out and record.time_in:
            # Convert to datetime objects for calculation
            time_in = datetime.combine(record.date, record.time_in)
            time_out = datetime.combine(record.date, record.time_out)
            duration = time_out - time_in
            
            # Format duration
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            record.duration = f"{int(hours)}h {int(minutes)}m"
        else:
            record.duration = None
    
    context = {
        'profile_user': profile_user,
        'attendance_stats': {
            'present_count': present_count,
            'late_count': late_count,
            'attendance_rate': attendance_rate,
        },
        'today_attendance': today_attendance,
        'recent_attendance': recent_attendance,
    }
    
    return render(request, 'attendance/view_user_profile.html', context)


@login_required
@user_passes_test(is_admin_user)
def edit_user_profile(request, user_id):
    """Edit user profile (admin only)"""
    profile_user = get_object_or_404(User, id=user_id, organization=request.user.organization)
    departments = Department.objects.filter(organization=request.user.organization)
    
    if request.method == 'POST':
        try:
            # Update user fields
            profile_user.first_name = request.POST.get('first_name', '').strip()
            profile_user.last_name = request.POST.get('last_name', '').strip()
            profile_user.email = request.POST.get('email', '').strip()
            profile_user.is_active = request.POST.get('is_active') == 'on'
            
            # Update position
            position = request.POST.get('position')
            if position in ['STAFF', 'MANAGER', 'ADMIN']:
                profile_user.position = position
            
            # Update department
            department_id = request.POST.get('department')
            if department_id:
                try:
                    department = Department.objects.get(
                        id=department_id, 
                        organization=request.user.organization
                    )
                    profile_user.department = department
                except Department.DoesNotExist:
                    messages.error(request, 'Invalid department selected.')
                    return redirect('edit_user_profile', user_id=user_id)
            else:
                profile_user.department = None
            
            profile_user.save()
            
            # Update profile fields (assuming you have a related Profile model)
            try:
                profile = profile_user.profile  # Fixed this line
                profile.save()
            except AttributeError:
                # Handle case where profile doesn't exist or isn't related
                pass
            
            messages.success(request, f'User profile for {profile_user.get_full_name()} updated successfully.')
            return redirect('user_management')  # or wherever you want to redirect
            
        except Exception as e:
            messages.error(request, f'Error updating user profile: {str(e)}')
            return redirect('edit_user_profile', user_id=user_id)
    
    # GET request - render the form
    context = {
        'profile_user': profile_user,
        'departments': departments,
    }
    return render(request, 'attendance/edit_user_profile.html', context)