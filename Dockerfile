# Use slim Python base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (needed for face-recognition, dlib, etc.)
RUN apt-get update && apt-get install -y \
    build-essential cmake gfortran git wget curl \
    libopenblas-dev liblapack-dev libatlas-base-dev \
    libjpeg-dev libpng-dev libtiff-dev \
    libavformat-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Upgrade pip
RUN pip install --upgrade pip

# Install PyTorch manually (since facenet-pytorch requires 2.2.x)
RUN pip install torch==2.2.0 torchvision==0.17.0

# Install other requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Start server with Gunicorn
# ⚠️ Replace "myproject" with your actual Django project folder name!
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:8000"]
