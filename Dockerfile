# Stage 1: Base image with minimal dependencies
FROM python:3.11-slim as base

# Set non-interactive frontend for apt
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libopenblas0 \
    libpq5 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: PyTorch installer (separate stage)
FROM base as torch_installer

# Install PyTorch CPU version first
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.0 \
    torchvision==0.17.0

# Stage 3: Face recognition builder
FROM base as face_builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dlib with optimizations
RUN pip install --no-cache-dir --user \
    dlib==19.24.2 \
    face-recognition==1.3.0

# Stage 4: Main application builder
FROM base as app_builder

WORKDIR /app
COPY requirements.txt .

# Install requirements in memory-efficient batches
RUN pip install --no-cache-dir \
    Django==5.0.6 \
    gunicorn==21.2.0 \
    whitenoise==6.6.0 \
    psycopg2-binary==2.9.9 && \
    pip install --no-cache-dir \
    dj-database-url==2.1.0 \
    djangorestframework==3.14.0 \
    crispy-bootstrap5==2023.10 && \
    pip install --no-cache-dir \
    django-extensions==3.2.3 \
    Pillow==10.2.0

# Stage 5: Final image
FROM base

# Copy artifacts from all stages
COPY --from=torch_installer /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=face_builder /root/.local /root/.local
COPY --from=app_builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app_builder /app /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PATH="/root/.local/bin:${PATH}"

# Clean up
RUN find /usr/local/lib/python3.11/site-packages -type d -name '__pycache__' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -type d -name 'tests' -exec rm -rf {} + && \
    find /usr/local -name "*.pyc" -delete && \
    find /usr/local -name "*.pyo" -delete

# Application setup
WORKDIR /app
RUN python manage.py collectstatic --noinput

EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]