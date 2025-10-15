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
# NOTE: This includes:
#   - tarsy/ (application code)
#   - alembic.ini (migration config - REQUIRED for production)
#   - alembic/ (migration scripts and env.py - REQUIRED for production)
COPY . .

# Accept VERSION build arg and inject into application
ARG VERSION=dev
ENV APP_VERSION=${VERSION}
RUN echo "${VERSION}" > /app/tarsy/VERSION

# Create a non-root user for security
RUN groupadd --gid 65532 appuser \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /bin/false appuser

# Create data and logs directories with proper ownership
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER 65532:65532

# Expose port
EXPOSE 8000

# Run application using make
CMD ["make", "run"]
