# dashboard/Dockerfile - Production Build
# Stage 1: Build React app
FROM mirror.gcr.io/library/node:24-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies including devDependencies for build
RUN npm ci --include=dev

# Copy source code
COPY . .

# Accept build arguments for environment variables
ARG VITE_API_BASE_URL
ARG VITE_WS_BASE_URL

# Set environment variables for build
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

# Build production bundle
RUN npm run build

# Stage 2: Serve with Nginx
FROM mirror.gcr.io/library/nginx:alpine

# Copy built React app from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration into the image
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create a non-root user for security
RUN addgroup -g 65532 -S appuser \
    && adduser -u 65532 -S -G appuser appuser

# Create nginx cache and run directories with proper ownership
RUN mkdir -p /var/cache/nginx/client_temp /var/run/nginx /run \
    && chown -R appuser:appuser /var/cache/nginx /var/run/nginx /usr/share/nginx/html /run

# Switch to non-root user
USER 65532:65532

# Expose port 8080 (non-privileged port)
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
