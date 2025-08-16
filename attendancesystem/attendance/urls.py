from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
from django.contrib.auth.decorators import login_required
from .views import get_ai_message_view, ai_feedback_view

urlpatterns = [
    # Public routes
    path('', views.home_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('login/face/', views.face_login_view, name='face_login'),
    path('login/face/verify/', views.verify_face_login, name='verify_face_login'),
    path('logout/', LogoutView.as_view(next_page='index'), name='logout'),
    path('signup/', views.signup_view, name='signup'),
    
    # Authenticated routes
    path('dashboard/', login_required(views.dashboard_view), name='dashboard'),
    path('register-face/', login_required(views.register_face_view), name='register_face'),
    path('mark-attendance/', login_required(views.mark_attendance), name='mark_attendance'),
    path('verify-attendance/', login_required(views.verify_face_attendance), name='verify_face_attendance'),
    path('face-detection-api/', views.face_detection_api, name='face_detection_api'),
    path('api/face-attendance/', views.verify_face_attendance, name='face_attendance_api'),
    path('register-face-api/', views.register_face_api, name='register_face_api'),
    path('get-ai-message/', get_ai_message_view, name='get_ai_message'),
    path('register-company/success/', views.registration_success, name='registration_success'),
    path('ai-feedback/', ai_feedback_view, name='ai_feedback'),
    path('register-company/', views.register_company, name='register_company'),
    path('get-departments/', views.get_departments, name='get_departments'),
    path('get-department-fields/', views.get_department_fields, name='get_department_fields'),

    # Profile management
    path('profile/', login_required(views.profile_view), name='profile'),
    path('profile/update/', login_required(views.profile_update_view), name='profile_update'),
    
    # Reports
    path('reports/', login_required(views.reports_view), name='reports'),
    path('reports/download/', login_required(views.download_report), name='download_report'),
    
    # Admin routes
    path('admin-dashboard/', login_required(views.admin_dashboard_view), name='admin_dashboard'),
    path('delete-user/<int:user_id>/', login_required(views.delete_user), name='delete_user'),
    path('clear-company-data/', login_required(views.clear_company_data), name='clear_company_data'),
    
        path('manage-departments/', views.manage_departments, name='manage_departments'),
    path('get-departments/', views.get_departments, name='get_departments'),
    
    # Invitations
    path('send-invitation/', views.send_invitation, name='send_invitation'),
    path('accept-invitation/<str:token>/', views.accept_invitation, name='accept_invitation'),
    
    # User management
    path('user/<int:user_id>/view/', views.view_user_profile, name='view_user_profile'),
    path('user/<int:user_id>/edit/', views.edit_user_profile, name='edit_user_profile'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)