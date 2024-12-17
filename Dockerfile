FROM ghcr.io/coqui-ai/tts-cpu

WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app

RUN pip install -r requirements.txt

RUN yes y | tts --list_language_idxs --model_name "tts_models/multilingual/multi-dataset/xtts_v2"

COPY . /app

RUN version=`date +"%s"` && \
    sed -i "s/%version%/${version}/g" /app/static/index.html

EXPOSE 8082

ENTRYPOINT ["python", "server.py"]

