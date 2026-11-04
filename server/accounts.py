"""
Accounts: register, log in, refresh tokens and log out.
"""
from http import HTTPStatus

from flask import current_app, request, session
from flask_restx import Namespace, Resource

import security.auth as auth
import security.refresh_tokens as refresh
from security.tokens import ACCESS_TOKEN_MINUTES, create_access_token

ns = Namespace('accounts', path='/')

MESSAGE = 'Message'
REGISTER_EP = '/register'
LOGIN_EP = '/login'
REFRESH_EP = '/refresh'
LOGOUT_EP = '/logout'


def _token_response(username, secret):
    return {
        'access_token': create_access_token(username, secret),
        'refresh_token': refresh.issue_refresh_token(username),
        'token_type': 'Bearer',
        'expires_in': ACCESS_TOKEN_MINUTES * 60,
    }


def _refresh_token():
    data = request.get_json(silent=True)
    token = data.get('refresh_token') if isinstance(data, dict) else None
    return token if isinstance(token, str) and token else None


def _credentials():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    username, password = data.get('username'), data.get('password')
    if not (isinstance(username, str) and isinstance(password, str)
            and username and password):
        return None
    return username, password


@ns.route(REGISTER_EP)
class Register(Resource):
    def post(self):
        """
        Create an account from JSON {username, password}.
        """
        creds = _credentials()
        if not creds:
            return {MESSAGE: 'username and password required'}, \
                HTTPStatus.BAD_REQUEST
        if not auth.register(*creds):
            return {MESSAGE: 'username taken'}, HTTPStatus.CONFLICT
        return {MESSAGE: 'registered'}, HTTPStatus.CREATED


@ns.route(LOGIN_EP)
class Login(Resource):
    def post(self):
        """
        Log in with JSON {username, password}; returns access and refresh
        tokens.
        """
        creds = _credentials()
        if not creds or not auth.login(*creds):
            return {MESSAGE: 'invalid credentials'}, HTTPStatus.UNAUTHORIZED
        secret = current_app.config.get('JWT_SECRET_KEY')
        if not secret:
            return {MESSAGE: 'Authentication unavailable'}, \
                HTTPStatus.SERVICE_UNAVAILABLE
        session.clear()
        return _token_response(creds[0], secret)


@ns.route(REFRESH_EP)
class Refresh(Resource):
    def post(self):
        """
        Swap JSON {refresh_token} for new access and refresh tokens.
        The old refresh token stops working.
        """
        # Checked first so a config problem doesn't use up the token.
        secret = current_app.config.get('JWT_SECRET_KEY')
        if not secret:
            return {MESSAGE: 'Authentication unavailable'}, \
                HTTPStatus.SERVICE_UNAVAILABLE
        token = _refresh_token()
        username = refresh.redeem_refresh_token(token) if token else None
        if not username:
            return {MESSAGE: 'Invalid or expired refresh token'}, \
                HTTPStatus.UNAUTHORIZED
        return _token_response(username, secret)


@ns.route(LOGOUT_EP)
class Logout(Resource):
    def post(self):
        """
        Log out; JSON {refresh_token} revokes that token.
        """
        token = _refresh_token()
        if token:
            refresh.revoke_refresh_token(token)
        session.clear()
        return {MESSAGE: 'logged out'}
