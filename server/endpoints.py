"""
This is the file that creates our flask app and wires up each feature.
Each feature lives in its own module with its own Namespace; add new
features there and register them below, instead of growing this file.
The endpoint called `endpoints` will return all available endpoints.
"""
import os

from flask import Flask
from flask_restx import Resource, Api
from flask_cors import CORS

from server import (accounts, follows, groups, meetup, neighborhoods,
                    rankings, restaurants, states, votes)

app = Flask(__name__)
# Set SECRET_KEY in prod; the random fallback resets sessions on restart.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
CORS(app)
api = Api(app, security='Bearer', authorizations={
    'Bearer': {'type': 'apiKey', 'in': 'header', 'name': 'Authorization'},
})

for feature in (accounts, follows, groups, meetup, neighborhoods, rankings,
                restaurants, states, votes):
    api.add_namespace(feature.ns)

ENDPOINT_EP = '/endpoints'
ENDPOINT_RESP = 'Available endpoints'
HEALTH_EP = '/health'
HELLO_EP = '/hello'
HELLO_RESP = 'hello'


@api.route(HEALTH_EP)
class Health(Resource):
    """Check that the server can reach its database, e.g. after a deploy."""
    def get(self):
        """
        Ping MongoDB. Reports whether the cloud or local database is in use,
        never the connection string.
        """
        import pymongo.errors
        import data.db_connect as dbc

        mode = ('cloud' if os.environ.get('CLOUD_MONGO', dbc.LOCAL)
                == dbc.CLOUD else 'local')
        try:
            # ponytail: uses the shared client's default 30s server
            # selection timeout, so a down database makes this slow to fail.
            dbc.connect_db().admin.command('ping')
        except (pymongo.errors.PyMongoError, ValueError):
            return {'db': 'unreachable', 'mode': mode}, 503
        return {'db': 'ok', 'mode': mode}


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


def create_app():
    """Initialize database indexes before serving requests."""
    from data.db_connect import initialize_indexes

    initialize_indexes()
    return app
