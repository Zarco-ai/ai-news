import logging
import os

from app import create_app


# Gunicorn imports this `app` object in production:
#   gunicorn "run:app" --bind 0.0.0.0:$PORT
app = create_app()

if __name__ == "__main__":
    # Local development only. Production uses gunicorn (see render.yaml).
    port = int(os.getenv("PORT", "8000"))
    logging.info("Flask app started (dev server) on port %s", port)
    app.run(host="0.0.0.0", port=port)