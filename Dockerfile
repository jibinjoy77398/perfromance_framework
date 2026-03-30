# Use the official Microsoft Playwright Python image as the base
# This image comes with Python and all browser dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

# Set the working directory in the container
WORKDIR /app

# Set environment variables
# 1. Prevent Python from writing .pyc files to disc
# 2. Prevent Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js and Lighthouse CLI
# 1. Update apt and install curl
# 2. Setup NodeSource and install Node.js
# 3. Install Lighthouse globally
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g lighthouse && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Re-verify playwright browsers are installed
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Create necessary directories for reports and database persistence
RUN mkdir -p reports web database config

# Expose port 8000 for the FastAPI dashboard/API
EXPOSE 8000

# Default command to run the application
# This starts the Performance Testing Framework in 'Server Mode'
CMD ["python", "run.py", "--serve", "--port", "8000"]
