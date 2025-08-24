FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install feedparser yt-dlp pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 youtube && \
    adduser -u 1000 -G youtube -s /bin/sh -D youtube

# Copy YouTube MCP server and lib directory
COPY mcp/youtube_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R youtube:youtube /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R youtube:youtube /data

# Switch to youtube user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the YouTube MCP server
ENTRYPOINT ["python", "youtube_server.py"]