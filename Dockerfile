FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt /app

RUN pip install -r requirements.txt



COPY . /app

RUN version=`date +"%s"` && \
    sed -i "s/%version%/${version}/g" /app/static/index.html

EXPOSE 8082

ENTRYPOINT ["python", "server.py"]

