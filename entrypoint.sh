#!/bin/bash
mkdir -p /app/.streamlit

python3 -c "
import os, sys
content = os.environ.get('STREAMLIT_SECRETS_TOML', '')
if content:
    with open('/app/.streamlit/secrets.toml', 'w') as f:
        f.write(content)
    print('secrets.toml written OK', flush=True)
else:
    print('WARNING: STREAMLIT_SECRETS_TOML is empty', flush=True)
"

exec streamlit run frontend.py \
    --server.port ${PORT:-8080} \
    --server.address 0.0.0.0 \
    --server.headless true