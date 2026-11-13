# ────────────────────────────────────────────────────────────────────────────────
# Multi-stage build for optimized image size
# ────────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies into a virtualenv that the final stage copies whole
# (a --user install under /root is invisible to the non-root runtime user)
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ────────────────────────────────────────────────────────────────────────────────
# Final production image
# ────────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

LABEL description="Serendipid API - AI-powered content analysis and archival"
LABEL version="1.0.0"

WORKDIR /app

# ──── Install runtime dependencies only ────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ──── Copy Python dependencies from builder ────
COPY --from=builder /opt/venv /opt/venv

# ──── Set environment variables ────
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# ──── Copy application code ────
COPY . .

# ──── Create necessary directories with proper permissions ────
RUN mkdir -p temp config static/thumbnails logs data/media uploads && \
    chmod 755 temp config static logs data uploads

# ──── Health check ────
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5050/ping || exit 1

# ──── Run as non-root user for security ────
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# ──── Expose port ────
EXPOSE 5050

# ──── Run the application ────
# One worker on purpose: the analysis queue, batch checks and background job
# state live in-process, and several workers would each run their own copy.
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5050", "--no-access-log"]
