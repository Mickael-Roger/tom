FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 weather && \
    adduser -u 1000 -G weather -s /bin/sh -D weather

# Copy weather MCP server and lib directory
COPY mcp/weather_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R weather:weather /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R weather:weather /data

# Switch to weather user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the weather MCP server
ENTRYPOINT ["python", "weather_server.py"]