FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests beautifulsoup4 pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 idfm && \
    adduser -u 1000 -G idfm -s /bin/sh -D idfm

# Copy IDFM MCP server and lib directory
COPY mcp/idfm_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R idfm:idfm /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R idfm:idfm /data

# Switch to idfm user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the IDFM MCP server
ENTRYPOINT ["python", "idfm_server.py"]