# Stage 1: Builder with build tools
FROM python:3.11-slim as builder

# Install build dependencies including CMake
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libopenblas0 \
    libjpeg62-turbo \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8000

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]