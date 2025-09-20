# backend/Dockerfile
FROM mirror.gcr.io/library/python:3.13-slim

WORKDIR /app

# Install system dependencies including Node.js for MCP servers
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Create data and logs directories
RUN mkdir -p /app/data /app/logs

# Expose port
EXPOSE 8000

# Run application using make
CMD ["make", "run"]
