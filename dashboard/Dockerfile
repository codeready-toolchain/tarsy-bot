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
ARG VERSION=dev

# Set environment variables for build
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL
ENV VITE_APP_VERSION=$VERSION

# Build production bundle
RUN npm run build

# Inject version into index.html (replace placeholder with actual version)
RUN sed -i "s/__APP_VERSION__/${VERSION}/g" /app/dist/index.html

# Stage 2: Serve with Nginx (unprivileged)
FROM mirror.gcr.io/nginxinc/nginx-unprivileged:alpine

# Copy built React app from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration into the image
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 8080 (non-privileged port)
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
