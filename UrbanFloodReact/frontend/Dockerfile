# Stage 1: Build the React application
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (for better caching)
COPY package.json package-lock.json* ./
RUN npm install

# Copy all frontend files
COPY . .

# Build the app to the 'dist' directory
RUN npm run build

# Stage 2: Serve the application with Nginx
FROM nginx:alpine

# Copy the built files to Nginx's html folder
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace default Nginx configuration to support client-side routing
RUN echo 'server { \
    listen 8080; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

# Run on port 8080 as required by Cloud Run
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
