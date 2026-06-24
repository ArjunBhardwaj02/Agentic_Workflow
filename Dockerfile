# 1. Base OS: We start with a lightweight, official Linux machine running Python 3.12
FROM python:3.12-slim

# 2. Set the working directory inside the container (like 'cd /app')
WORKDIR /app

# 3. System Dependencies: Postgres drivers (psycopg) require C-compilers on Linux
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy the requirements file FIRST. 
# (Docker caches steps. If you change ui.py, it won't reinstall all libraries if requirements.txt hasn't changed).
COPY requirements.txt .

# 5. Install the exact same 'uv' package manager you use locally, then install your dependencies
RUN pip install uv
RUN uv pip install --system -r requirements.txt

# 6. Copy your actual Python code and MCP servers into the container
COPY . .

# 7. Expose port 8501 (The default port Streamlit uses to broadcast to the internet)
EXPOSE 8501

# 8. The Ignition Switch: The exact terminal command to run when the container boots
CMD ["streamlit", "run", "frontend.py", "--server.port=8501", "--server.address=0.0.0.0"]