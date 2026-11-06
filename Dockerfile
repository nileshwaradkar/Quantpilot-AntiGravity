# Quant Pilot - Multi-Cloud Dockerfile
# Optimized for Free Deployments: Hugging Face Spaces (Port 7860) & Render / Railway (Port $PORT)

FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose default port
EXPOSE 7860

# Run FastAPI via main.py (dynamically listens on $PORT)
CMD ["python", "main.py"]
