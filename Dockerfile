FROM python:3.13-alpine

WORKDIR /app

# Install build dependencies for Alpine
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    g++ \
    gfortran \
    openblas-dev \
    lapack-dev

COPY requirements.txt /app

# Upgrade pip and install packages
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt



COPY . /app

RUN version=`date +"%s"` && \
    sed -i "s/%version%/${version}/g" /app/static/index.html

EXPOSE 8082

ENTRYPOINT ["python", "server.py"]

