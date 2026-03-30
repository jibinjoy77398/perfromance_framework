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
RUN apt-get update && apt-get install -y curl gnupg && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y nodejs && \
    npm install -g lighthouse && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/bin:${PATH}"

# Re-verify playwright browsers and OS dependencies are installed
RUN playwright install --with-deps chromium

# Link Playwright Chromium to system path so Lighthouse can find it
RUN ln -s $(find /ms-playwright -name chrome -executable -type f | head -n 1) /usr/bin/google-chrome || true

# Copy the rest of the application code
COPY . .

# Create necessary directories for reports and database persistence
RUN mkdir -p reports web database config

# Expose port 8000 for the FastAPI dashboard/API
EXPOSE 8000

# Default command to run the application
# This starts the Performance Testing Framework in 'Server Mode'
CMD ["python", "run.py", "--serve", "--port", "8000"]
