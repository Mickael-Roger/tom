FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests beautifulsoup4 pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 cafetaria && \
    adduser -u 1000 -G cafetaria -s /bin/sh -D cafetaria

# Copy cafetaria MCP server and lib directory
COPY mcp/cafetaria_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R cafetaria:cafetaria /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R cafetaria:cafetaria /data

# Switch to cafetaria user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the cafetaria MCP server
ENTRYPOINT ["python", "cafetaria_server.py"]