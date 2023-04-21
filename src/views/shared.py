"""
Shared global views.
"""

# =============================================================================

import db
from utils import fetch_tms
from utils.auth import set_redirect_page
from utils.server import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/", methods=["GET"])
def index():
    set_redirect_page()
    return _render("index.jinja")


@app.route("/matches_status", methods=["GET"])
def view_matches_status():
    set_redirect_page()

    matches_statuses = db.match_status.get_matches_status()

    # sort by match number
    hundreds = []
    ordered_statuses = []
    last_hundred = None
    for match_number, match_status in sorted(
        matches_statuses.items(),
        key=lambda pair: fetch_tms.match_number_sort_key(pair[0]),
    ):
        match_number_hundred = match_number // 100
        hundred_str = f"{match_number_hundred}00"
        if last_hundred is None or match_number_hundred != last_hundred:
            last_hundred = match_number_hundred
            hundreds.append(hundred_str)
        match_status["hundred_str"] = hundred_str
        ordered_statuses.append(match_status)

    return _render(
        "/notifications/matches_status.jinja",
        hundreds=hundreds,
        statuses=ordered_statuses,
        status_accents=fetch_tms.MATCH_STATUS_TABLE_ACCENTS,
    )
