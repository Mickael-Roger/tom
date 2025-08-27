FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Create non-root user
RUN useradd -u 1000 -m test_user

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for MCP testing
RUN pip install --no-cache-dir \
    mcp \
    fastmcp \
    requests \
    pyyaml \
    json-rpc \
    litellm \
    flask

# Copy required files and directories
COPY mcp/ /app/mcp/
COPY lib/ /app/lib/
COPY tests/ /app/tests/
COPY tom.py /app/tom.py

# Set ownership
RUN chown -R test_user:test_user /app

# Expose port 80 for web interface
EXPOSE 80

# Switch to non-root user
USER test_user

# Default command starts the web dashboard
CMD ["python", "/app/tests/web_dashboard.py"]