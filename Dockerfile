# Stage 1: Base image with minimal dependencies
FROM python:3.11-slim as base

# Install only essential runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libopenblas0 \
    libpq5 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: CPU-only PyTorch installation
FROM base as builder

WORKDIR /app
COPY requirements.txt .

# Install CPU-only versions of heavy packages first
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu \
    torchvision==0.17.0+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install remaining requirements
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final image
FROM base

WORKDIR /app

# Copy installed packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app /app

# Environment setup
ENV PYTHONUNBUFFERED=1 \
    PORT=8000

# Clean up
RUN find /usr/local/lib/python3.11/site-packages -type d -name '__pycache__' -exec rm -rf {} + && \
    find /usr/local/lib/python3.11/site-packages -type d -name 'tests' -exec rm -rf {} +

# Application setup
RUN python -m pip install --no-deps -e . && \
    python manage.py collectstatic --noinput

EXPOSE $PORT
CMD ["gunicorn", "attendancesystem.wsgi:application", "--bind", "0.0.0.0:$PORT"]