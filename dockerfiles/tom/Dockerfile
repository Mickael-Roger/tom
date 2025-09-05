FROM python:3.13-alpine

WORKDIR /app

# Install build dependencies for Alpine
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers

# Create user with UID 1000
RUN addgroup -g 1000 tom && \
    adduser -u 1000 -G tom -s /bin/sh -D tom

# Copy requirements and install Python packages as root
COPY requirements.txt /app/
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application files
COPY tom.py /app/
COPY lib/ /app/lib/
COPY static/ /app/static/

# Set version in static files
RUN version=`date +"%s"` && \
    sed -i "s/%version%/${version}/g" /app/static/index.html

# Set permissions for app directory
# Note: /data will be mounted from host, so we don't create it here
RUN chown -R tom:tom /app

# Switch to tom user
USER 1000

# Expose port 443
EXPOSE 443

# Run the application
ENTRYPOINT ["python", "tom.py"]