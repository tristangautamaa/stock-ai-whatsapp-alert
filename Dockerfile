FROM python:3.11-slim-bullseye

WORKDIR /app

# Install system dependencies needed for pandas/numpy compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements-render.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements-render.txt

# Copy project
COPY . .

# Default command (overridden by Render cron)
CMD ["python", "-m", "src.report.send_brief"]
