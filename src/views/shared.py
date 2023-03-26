"""
Shared global views.
"""

# =============================================================================

from utils.auth import set_redirect_page
from utils.server import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/", methods=["GET"])
def index():
    set_redirect_page()
    return _render("index.jinja")
