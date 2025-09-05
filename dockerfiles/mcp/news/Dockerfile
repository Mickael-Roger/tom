FROM python:3.13-alpine

WORKDIR /app

# Install dependencies
RUN pip install --upgrade pip && \
    pip install requests beautifulsoup4 pyyaml mcp fastmcp

# Create user with UID 1000
RUN addgroup -g 1000 tomnews && \
    adduser -u 1000 -G tomnews -s /bin/sh -D tomnews

# Copy news MCP server, scraping extensions, and lib directory
COPY mcp/news_server.py /app/
COPY mcp/news_scrape/ /app/news_scrape/
COPY lib/ /app/lib/

# Set permissions
RUN chown -R tomnews:tomnews /app

# Create data directory and set permissions
RUN mkdir -p /data && chown -R tomnews:tomnews /data

# Switch to news user
USER 1000

# Expose port 80 for HTTP MCP server
EXPOSE 80

# Run the news MCP server
ENTRYPOINT ["python", "news_server.py"]
