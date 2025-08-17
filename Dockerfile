# Stage 1: Face recognition builder
FROM python:3.11-slim as face_builder

# Install minimal build dependencies
RUN apt-get update && \
    apt-get install -y \
    cmake \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pre-built dlib wheel to avoid compilation
RUN pip install --no-cache-dir --user \
    https://files.pythonhosted.org/packages/0e/ce/f8a3cff33ac03a8219768f0694c5d703c8e037e6aba2e865f9bae22ed63c/dlib-19.24.2-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
    face-recognition==1.3.0

# Stage 2: Main application builder
FROM python:3.11-slim as app_builder

# Install remaining build dependencies
RUN apt-get update && \
    apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install CPU-only PyTorch first
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu \
    torchvision==0.17.0+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install other requirements (excluding face-recognition)
RUN pip install --no-cache-dir -r <(grep -v "face-recognition" requirements.txt)

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

# Clean up
RUN find /usr/local/lib/python3.11/site-packages -type d -name '__pycache__' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -type d -name 'tests' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -name '*.so' -exec strip {} \;

# Application setup
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8000
RUN python manage.py collectstatic --noinput

EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]