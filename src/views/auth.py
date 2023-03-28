"""
Views for authentication through Google and authorization.
"""

# =============================================================================

import json
import os

import requests
from flask import redirect, request, session, url_for
from oauthlib.oauth2 import WebApplicationClient

from utils.auth import _redirect_last
from utils.server import AppRoutes

# =============================================================================

app = AppRoutes()

REQUEST_TIMEOUT = 60

GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# OAuth2 client
oauth2_client = WebApplicationClient(GOOGLE_CLIENT_ID)

# =============================================================================


def _get_google_provider_cfg(*keys):
    if len(keys) == 0:
        return None
    google_provider_cfg = requests.get(
        GOOGLE_DISCOVERY_URL, timeout=REQUEST_TIMEOUT
    ).json()
    if len(keys) == 1:
        return google_provider_cfg[keys[0]]
    return [google_provider_cfg[key] for key in keys]


@app.route("/login", methods=["GET"])
def log_in():
    # determine the URL for Google login
    authorization_endpoint = _get_google_provider_cfg("authorization_endpoint")

    # get the request URL for Google login including user data scopes
    request_uri = oauth2_client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email"],
    )

    # redirect to login page
    return redirect(request_uri)


@app.route("/login/callback", methods=["GET"])
def login_callback():
    # get authorization code from Google
    auth_code = request.args.get("code")

    # determine the URL for fetching the tokens and user data
    token_endpoint, user_info_endpoint = _get_google_provider_cfg(
        "token_endpoint", "userinfo_endpoint"
    )

    # fetch and parse the tokens
    token_url, headers, body = oauth2_client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=auth_code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
        timeout=REQUEST_TIMEOUT,
    )
    oauth2_client.parse_request_body_response(
        json.dumps(token_response.json())
    )

    # fetch the user's data
    user_info_uri, headers, body = oauth2_client.add_token(user_info_endpoint)
    user_info = requests.get(
        user_info_uri, headers=headers, data=body, timeout=REQUEST_TIMEOUT
    ).json()

    # user_info: {
    #   "sub": unique identifier from Google,
    #   "picture": profile picture url,
    #   "email": email,
    #   "email_verified": True or False,
    # }

    if not user_info.get("email_verified", False):
        return "User email not available or not verified by Google.", 400

    # save user as logged in
    if user_info.get("email", None) is None:
        return "User email could not be found.", 400

    session["email"] = user_info["email"]
    session["user_info"] = user_info

    return _redirect_last()


@app.route("/logout", methods=["GET"])
def log_out():
    # clear logged in user from the session
    session.pop("email", None)
    session.pop("user_info", None)
    # after logging out, redirect to index
    return redirect(url_for("index"))
