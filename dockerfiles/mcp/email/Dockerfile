FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install requests pyyaml mcp fastmcp

# Create user with UID 1000
RUN groupadd -g 1000 tommail && \
    useradd -u 1000 -g tommail -s /bin/bash -m tommail

# Copy mail MCP server and lib directory
COPY mcp/mail_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R tommail:tommail /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R tommail:tommail /data

# Switch to mail user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the mail MCP server
ENTRYPOINT ["python", "mail_server.py"]
