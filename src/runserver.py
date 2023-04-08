"""
Runs a development server in debug mode.

For HTTPS, you must have a `cert.pem` and `key.pem` file in the root
directory.

You also must have the environment variables `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` set for authentication through Google.
"""

# =============================================================================

import os

# Set `FLASK_DEBUG` so that the app is initialized in debug mode
# Expects any string
os.environ["FLASK_DEBUG"] = "True"

from app import app  # pylint: disable=wrong-import-position

# =============================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, ssl_context=("cert.pem", "key.pem"))
