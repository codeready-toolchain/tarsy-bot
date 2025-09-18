# dashboard/Dockerfile - Development Mode
FROM mirror.gcr.io/library/node:24-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies including devDependencies for development
RUN npm ci --include=dev

# Copy source code
COPY . .

# Expose port
EXPOSE 3000

# Run development server with Vite proxy
CMD ["npx", "vite", "dev", "--host", "0.0.0.0", "--port", "3000"]
