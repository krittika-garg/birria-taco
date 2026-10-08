"""
This is the file containing all of the endpoints for our flask app.
The endpoint called `endpoints` will return all available endpoints.
"""
import os
from http import HTTPStatus

from flask import Flask, request, session
from flask_restx import Resource, Api  # , fields  # Namespace
from flask_cors import CORS

# import werkzeug.exceptions as wz

import security.auth as auth

app = Flask(__name__)
# Set SECRET_KEY in prod; the random fallback resets sessions on restart.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
CORS(app)
api = Api(app)

ENDPOINT_EP = '/endpoints'
ENDPOINT_RESP = 'Available endpoints'
HELLO_EP = '/hello'
HELLO_RESP = 'hello'
MESSAGE = 'Message'
REGISTER_EP = '/register'
LOGIN_EP = '/login'
LOGOUT_EP = '/logout'


@api.route(HELLO_EP)
class HelloWorld(Resource):
    """
    The purpose of the HelloWorld class is to have a simple test to see if the
    app is working at all.
    """
    def get(self):
        """
        A trivial endpoint to see if the server is running.
        """
        return {HELLO_RESP: 'world'}


@api.route(ENDPOINT_EP)
class Endpoints(Resource):
    """
    This class will serve as live, fetchable documentation of what endpoints
    are available in the system.
    """
    def get(self):
        """
        The `get()` method will return a sorted list of available endpoints.
        """
        endpoints = sorted(rule.rule for rule in api.app.url_map.iter_rules())
        return {"Available endpoints": endpoints}


def _credentials():
    data = request.get_json(silent=True) or {}
    username, password = data.get('username'), data.get('password')
    if not (isinstance(username, str) and isinstance(password, str)
            and username and password):
        return None
    return username, password


@api.route(REGISTER_EP)
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


@api.route(LOGIN_EP)
class Login(Resource):
    def post(self):
        """
        Log in with JSON {username, password}; sets a session cookie.
        """
        creds = _credentials()
        if not creds or not auth.login(*creds):
            return {MESSAGE: 'invalid credentials'}, HTTPStatus.UNAUTHORIZED
        session['user'] = creds[0]
        return {MESSAGE: 'logged in'}


@api.route(LOGOUT_EP)
class Logout(Resource):
    def post(self):
        session.clear()
        return {MESSAGE: 'logged out'}
