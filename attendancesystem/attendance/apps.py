from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "attendance"

# python manage.py flush  # Clear all data
# python manage.py migrate --fake attendance zero  # Reset migration state
# python manage.py migrate 