FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Configure Git inside container for SSH pushes
RUN git config --global user.name "Volcano Observer Agent" && \
    git config --global user.email "observer@volcano.local" && \
    git config --global url."git@github.com:".insteadOf "https://github.com/" && \
    git config --global --add safe.directory '*' && \
    mkdir -p -m 0700 /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null || true

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
