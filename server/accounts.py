"""
Accounts: register, log in (issues a JWT) and log out.
"""
from http import HTTPStatus

from flask import current_app, request, session
from flask_restx import Namespace, Resource

import security.auth as auth
from security.tokens import ACCESS_TOKEN_MINUTES, create_access_token

ns = Namespace('accounts', path='/')

MESSAGE = 'Message'
REGISTER_EP = '/register'
LOGIN_EP = '/login'
LOGOUT_EP = '/logout'


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
        Log in with JSON {username, password}; returns a JWT access token.
        """
        creds = _credentials()
        if not creds or not auth.login(*creds):
            return {MESSAGE: 'invalid credentials'}, HTTPStatus.UNAUTHORIZED
        secret = current_app.config.get('JWT_SECRET_KEY')
        if not secret:
            return {MESSAGE: 'Authentication unavailable'}, \
                HTTPStatus.SERVICE_UNAVAILABLE
        session.clear()
        return {
            'access_token': create_access_token(creds[0], secret),
            'token_type': 'Bearer',
            'expires_in': ACCESS_TOKEN_MINUTES * 60,
        }


@ns.route(LOGOUT_EP)
class Logout(Resource):
    def post(self):
        session.clear()
        return {MESSAGE: 'logged out'}
