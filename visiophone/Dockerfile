FROM python:3.12-alpine

RUN pip install --no-cache-dir "paho-mqtt>=2.1" "requests>=2.32"

WORKDIR /app
COPY bridge.py /app/bridge.py

CMD ["python", "-u", "/app/bridge.py"]
