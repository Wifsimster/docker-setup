FROM node:22-slim

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv git openssh-client && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

RUN python3 -m venv /app/venv
COPY requirements.txt .
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .

USER node

CMD ["/app/venv/bin/python", "-u", "agent.py"]
