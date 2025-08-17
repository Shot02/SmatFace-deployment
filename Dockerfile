# Stage 1: Face recognition builder (most space-intensive)
FROM python:3.11-slim as face_builder

# Install minimal build dependencies
RUN apt-get update && \
    apt-get install -y \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install only face_recognition and its direct dependencies
RUN pip install --no-cache-dir --user \
    dlib==19.24.2 \
    face-recognition==1.3.0 \
    face-recognition-models==0.3.0

# Stage 2: Main application builder
FROM python:3.11-slim as app_builder

# Install remaining build dependencies
RUN apt-get update && \
    apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install CPU-only PyTorch and other requirements
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu \
    torchvision==0.17.0+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html && \
    pip install --no-cache-dir -r requirements.txt

# Stage 3: Final image
FROM python:3.11-slim

# Minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libopenblas0 \
    libpq5 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary artifacts
COPY --from=face_builder /root/.local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app_builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app_builder /app /app

# Clean up Python cache
RUN find /usr/local/lib/python3.11/site-packages -type d -name '__pycache__' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -type d -name 'tests' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -name '*.so' -exec strip {} \;

# Application setup
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8000
RUN python manage.py collectstatic --noinput

EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]