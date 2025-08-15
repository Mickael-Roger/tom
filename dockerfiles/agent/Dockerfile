FROM python:3.13-alpine

# Create user with UID 1000
RUN addgroup -g 1000 tom && \
    adduser -u 1000 -G tom -s /bin/sh -D tom

USER 1000

# Run the application
ENTRYPOINT ["/bin/sleep", "9999999999"]
