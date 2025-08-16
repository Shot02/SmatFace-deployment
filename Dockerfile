# Stage 1: Builder for face_recognition dependencies
FROM python:3.11-slim as face_builder

RUN apt-get update && \
    apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --user dlib==19.24.2 face_recognition==1.3.0

# Stage 2: Main builder
FROM python:3.11-slim as builder

# Install only essential build dependencies
RUN apt-get update && \
    apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 3: Final image
FROM python:3.11-slim

# Minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libopenblas0 \
    libpq5 \
    libjpeg62-turbo \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary artifacts
COPY --from=face_builder /root/.local/lib/python3.11/site-packages /root/.local/lib/python3.11/site-packages
COPY --from=builder /root/.local /root/.local
COPY . .

# Environment setup
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Cleanup
RUN find /root/.local -type d -name '__pycache__' -exec rm -rf {} + && \
    find /root/.local -type d -name 'tests' -exec rm -rf {} + && \
    find /root/.local -type f -name '*.py[co]' -delete

# Application setup
RUN python manage.py collectstatic --noinput
EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]