FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests beautifulsoup4 pyyaml mcp fastmcp mygpoclient

# Create user with UID 1000
RUN addgroup -g 1000 tomgpodder && \
    adduser -u 1000 -G tomgpodder -s /bin/sh -D tomgpodder

# Copy gpodder MCP server and lib directory
COPY mcp/gpodder_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R tomgpodder:tomgpodder /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R tomgpodder:tomgpodder /data

# Switch to gpodder user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the gpodder MCP server
ENTRYPOINT ["python", "gpodder_server.py"]