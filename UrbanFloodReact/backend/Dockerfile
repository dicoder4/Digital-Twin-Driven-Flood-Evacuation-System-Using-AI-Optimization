FROM python:3.10-slim

# Install system dependencies required for geospatial libraries (osmnx, rtree, geopandas, etc.)
RUN apt-get update && apt-get install -y \
    libexpat1 \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code explicitly including cache
COPY . .

# Expose the port Cloud Run expects
EXPOSE 8080

# Start server
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
