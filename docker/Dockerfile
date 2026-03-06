FROM python:3.12-slim

# System dependencies: ffmpeg (audio conversion), lsof (port cleanup at startup)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg lsof \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (exclude selenium/webdriver-manager — no browser in container)
COPY requirements.txt .
RUN grep -viE 'selenium|webdriver.manager' requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && rm requirements-docker.txt requirements.txt

# Copy application files
COPY music-porter release-notes.txt ./
COPY server/ server/

# Pre-create data directories for volume mounts
RUN mkdir -p library logs data

# Real-time output for SSE streaming and logs
ENV PYTHONUNBUFFERED=1

EXPOSE 5555

COPY docker/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["server"]
