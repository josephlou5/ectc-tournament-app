"""
Views for an admin that are not the Admin Settings or Notifications
pages.
"""

# =============================================================================

import db
from utils.auth import login_required
from utils.server import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/sent_emails", methods=["GET"])
@login_required(admin=True)
def view_sent_emails():
    sent_emails = db.sent_emails.get_all_sent_emails()
    return _render("/admin/sent_emails.jinja", sent_emails=sent_emails)
