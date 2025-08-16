# Stage 1: Builder stage
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libopenblas0 \
    liblapack3 \
    libjpeg-dev \
    libpng-dev \
    libpq5 \
    libsm6 \
    libxext6 \
    libxrender-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
COPY . .

# Ensure Python can find the user-installed packages
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages

# Collect static files
RUN python manage.py collectstatic --noinput

# Set up the application
ENV PORT=8000
EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT", "--workers=2"]