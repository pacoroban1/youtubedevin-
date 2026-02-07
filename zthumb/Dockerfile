# Z-Image Thumbnail Engine Dockerfile
#
# NOTE: This image must run on CPU-only + Apple Silicon (linux/arm64) as well as
# GPU Linux boxes. We default to a multi-arch Python base image; GPU users can
# override BASE_IMAGE at build time.
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ ./server/
COPY backends/ ./backends/
COPY scripts/ ./scripts/

# Create directories for models and outputs
RUN mkdir -p /models /outputs

# Set environment variables
ENV ZTHUMB_MODELS_DIR=/models
ENV ZTHUMB_OUTPUTS_DIR=/outputs

# Expose port
EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

# Run the server
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8100"]
