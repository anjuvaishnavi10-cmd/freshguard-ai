# ==============================================================================
# FreshGuard AI — Production Container Image
# GDGoC HITAM Agentic AI Hackathon
# ==============================================================================

FROM python:3.11-slim

WORKDIR /app

# Optimize Python execution in containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Copy dependency manifest and install optional packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy application source code
COPY . .

# Expose default container port
EXPOSE 8080

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://localhost:{port}/api/health')" || exit 1

# Start FreshGuard AI server
CMD ["python", "server.py"]
