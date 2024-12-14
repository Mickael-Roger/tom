FROM ghcr.io/coqui-ai/tts-cpu

WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app

RUN pip install -r requirements.txt

COPY . /app

EXPOSE 8082

ENTRYPOINT ["python", "server.py"]

