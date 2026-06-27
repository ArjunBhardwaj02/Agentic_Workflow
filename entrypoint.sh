#!/bin/bash
mkdir -p /app/.streamlit
echo "$STREAMLIT_SECRETS_TOML" > /app/.streamlit/secrets.toml
exec streamlit run frontend.py \
    --server.port ${PORT:-8080} \
    --server.address 0.0.0.0 \
    --server.headless true