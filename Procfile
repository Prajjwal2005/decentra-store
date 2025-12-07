# Procfile - Process definitions for deployment
# Used by Railway, Render, Heroku, and similar platforms

# Web process (Backend + Frontend)
web: python -m backend.app --host 0.0.0.0 --port ${PORT:-5000}

# Discovery service (run as separate service or worker)
discovery: python -m discovery.server --host 0.0.0.0 --port ${DISCOVERY_PORT:-4000}
