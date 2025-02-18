import os
import talisker
import flask

from canonicalwebteam.store_api.stores.charmstore import CharmPublisher
from flask_wtf.csrf import generate_csrf, validate_csrf

from canonicalwebteam.candid import CandidClient
from webapp.helpers import is_safe_url
from webapp import authentication

login = flask.Blueprint(
    "login", __name__, template_folder="/templates", static_folder="/static"
)

LOGIN_URL = os.getenv("LOGIN_URL", "https://login.ubuntu.com")
LOGIN_LAUNCHPAD_TEAM = os.getenv(
    "LOGIN_LAUNCHPAD_TEAM", "canonical-webmonkeys"
)


request_session = talisker.requests.get_session()
candid = CandidClient(request_session)
publisher_api = CharmPublisher(request_session)


@login.route("/logout")
def logout():
    authentication.empty_session(flask.session)
    return flask.redirect("/")


@login.route("/login/")
def publisher_login():
    # Get a bakery v2 macaroon from the publisher API to be discharged
    # and save it in the session
    flask.session["publisher-macaroon"] = publisher_api.issue_macaroon()

    login_url = candid.get_login_url(
        macaroon=flask.session["publisher-macaroon"],
        callback_url=flask.url_for("login.login_callback", _external=True),
        state=generate_csrf(),
    )

    # Next URL to redirect the user after the login
    next_url = flask.request.args.get("next")

    if next_url:
        if not is_safe_url(next_url):
            return flask.abort(400)
        flask.session["next_url"] = next_url

    return flask.redirect(login_url, 302)


@login.route("/login/callback")
def login_callback():
    code = flask.request.args["code"]
    state = flask.request.args["state"]

    # Avoid CSRF attacks
    validate_csrf(state)

    discharged_token = candid.discharge_token(code)
    candid_macaroon = candid.discharge_macaroon(
        flask.session["publisher-macaroon"], discharged_token
    )

    # Store bakery authentication
    issued_macaroon = candid.get_serialized_bakery_macaroon(
        flask.session["publisher-macaroon"], candid_macaroon
    )

    flask.session["publisher-auth"] = publisher_api.exchange_macaroons(
        issued_macaroon
    )

    flask.session["publisher"] = publisher_api.whoami(
        flask.session["publisher-auth"]
    )

    return flask.redirect(
        flask.session.pop(
            "next_url",
            "/charms",
        ),
        302,
    )
