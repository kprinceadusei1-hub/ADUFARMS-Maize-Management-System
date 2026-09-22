"""Run ADUFARMS with a production WSGI server on Windows."""
import os

from waitress import serve

import app


if __name__ == "__main__":
    app.init_db()
    serve(
        app.app,
        host=os.environ.get("ADUFARMS_HOST", "127.0.0.1"),
        port=int(os.environ.get("ADUFARMS_PORT", "5000")),
        threads=int(os.environ.get("ADUFARMS_THREADS", "4")),
        channel_timeout=int(os.environ.get("ADUFARMS_CHANNEL_TIMEOUT", "120")),
    )
