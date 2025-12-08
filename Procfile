# Procfile - Process definitions for deployment
# Used by Railway, Render, Heroku, and similar platforms

# Web process with WebSocket support via gevent
web: gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:${PORT:-5000} server:app
