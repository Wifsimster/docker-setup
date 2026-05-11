FROM shenxn/protonmail-bridge:latest

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libfido2-1 \
    && rm -rf /var/lib/apt/lists/*
