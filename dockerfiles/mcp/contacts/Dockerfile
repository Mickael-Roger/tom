FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 contacts && \
    adduser -u 1000 -G contacts -s /bin/sh -D contacts

# Copy contacts MCP server and lib directory
COPY mcp/contacts_server.py /app/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R contacts:contacts /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R contacts:contacts /data

# Switch to contacts user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the contacts MCP server
ENTRYPOINT ["python", "contacts_server.py"]