#!/bin/bash
mkdir -p /app/.streamlit

# Only write from env var if set (Cloud Run)
# Otherwise use mounted file (local Docker)
if [ -n "$STREAMLIT_SECRETS_TOML" ]; then
    printf '%s' "$STREAMLIT_SECRETS_TOML" > /app/.streamlit/secrets.toml
fi

exec streamlit run frontend.py \
    --server.port ${PORT:-8080} \
    --server.address 0.0.0.0 \
    --server.headless true