    # 1. Base OS
    FROM python:3.12-slim

    # 2. Set the working directory inside the container
    WORKDIR /app

    # 3. CRITICAL SYSTEM DEPENDENCIES (Added curl, Node.js, and Notion Server)
    RUN apt-get update && apt-get install -y \
        gcc \
        libpq-dev \
        curl \
        && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
        && apt-get install -y nodejs \
        && npm install -g @notionhq/notion-mcp-server \
        && rm -rf /var/lib/apt/lists/*

    # 4. Install 'uv' explicitly via its official installer
    RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

    # 5. Copy requirements
    COPY requirements.txt .

    # 6. Install Python dependencies
    RUN uv pip install --system -r requirements.txt

    # 7. Copy application code
    COPY . .

    # 8. Expose Port (Cloud Run expects 8080)
    EXPOSE 8080

    ENV PORT=8080

    # 9. Ignition Switch
    CMD streamlit run frontend.py \
        --server.port $PORT \
        --server.address 0.0.0.0 \
        --server.headless true