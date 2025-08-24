FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install firebase-admin mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 notifications && \
    adduser -u 1000 -G notifications -s /bin/sh -D notifications

# Copy notifications MCP server and lib directory
COPY mcp/notifications_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R notifications:notifications /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R notifications:notifications /data

# Switch to notifications user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the notifications MCP server
ENTRYPOINT ["python", "notifications_server.py"]