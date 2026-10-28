"""
This is the file containing all of the endpoints for our flask app.
The endpoint called `endpoints` will return all available endpoints.
"""
import os
from http import HTTPStatus

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, g, request, session
from flask_restx import Resource, Api  # , fields  # Namespace
from flask_cors import CORS

# import werkzeug.exceptions as wz

import data.db_connect as dbc
import security.auth as auth
from security.jwt_auth import login_required
from security.tokens import ACCESS_TOKEN_MINUTES, create_access_token
from places.load import NEIGHBORHOOD, PLACES_COLLECT, geo_point
from math import atan2, cos, isfinite, radians, sin, sqrt

app = Flask(__name__)
# Set SECRET_KEY in prod; the random fallback resets sessions on restart.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
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
STATES_EP = '/states'
STATES_RESP = 'states'
STATES_COLLECT = 'states'
RESTAURANTS_EP = '/restaurants'
RESTAURANT_EP = '/restaurants/<string:resid>'
RESTAURANTS_COLLECT = 'restaurants'
NEIGHBORHOOD_AT_EP = '/neighborhoods/at'


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


@api.route(STATES_EP)
class States(Resource):
    def get(self):
        """
        Return all states loaded by states/load.py.
        """
        dbc.connect_db()
        return {STATES_RESP: dbc.read(STATES_COLLECT)}


@api.route('/states/<string:abbrev>')
class State(Resource):
    def get(self, abbrev):
        """Return one state by its abbreviation."""
        dbc.connect_db()
        state = dbc.read_one(
            STATES_COLLECT,
            {'Abbrev': abbrev.upper()},
        )
        if state is None:
            return {MESSAGE: 'State not found'}, HTTPStatus.NOT_FOUND
        state.pop('_id', None)
        return {'state': state}


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in kilometers."""
    lat1, lon1, lat2, lon2 = map(
        radians, (lat1, lon1, lat2, lon2)
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    a = max(0.0, min(1.0, a))
    return 6371.0 * 2 * atan2(sqrt(a), sqrt(1 - a))


LAT_LON_NUMERIC_ERROR = 'Provide numeric lat and lon query parameters'
LAT_LON_BODY_NUMERIC_ERROR = 'lat and lon must be numbers'
LAT_LON_RANGE_ERROR = ('lat must be between -90 and 90; '
                       'lon must be between -180 and 180')


def _lat_lon_error(lat, lon):
    """
    Return LAT_LON_RANGE_ERROR if lat or lon is non-finite or out of
    range, else None.
    """
    # Range first: isfinite() overflows on huge ints from a JSON body.
    if (
        not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or not isfinite(lat)
        or not isfinite(lon)
    ):
        return LAT_LON_RANGE_ERROR
    return None


def _parse_lat_lon():
    """
    Read lat and lon from the query string.
    Returns ((lat, lon), None) on success, or (None, error_message)
    on failure.
    """
    try:
        lat = float(request.args.get('lat', ''))
        lon = float(request.args.get('lon', ''))
    except (TypeError, ValueError):
        return None, LAT_LON_NUMERIC_ERROR

    error = _lat_lon_error(lat, lon)
    if error:
        return None, error
    return (lat, lon), None


def find_neighborhood(lat, lon):
    """
    Return the neighborhood whose boundary contains lat, lon, without
    _id and boundary, or None if no neighborhood contains it.
    """
    dbc.connect_db()
    neighborhood = dbc.read_one(PLACES_COLLECT, {
        'type': NEIGHBORHOOD,
        'boundary': {'$geoIntersects': {'$geometry': geo_point(lat, lon)}},
    })
    if neighborhood is None:
        return None
    neighborhood.pop('_id', None)
    neighborhood.pop('boundary', None)
    return neighborhood


@api.route('/states/nearest')
class NearestState(Resource):
    def get(self):
        """
        Return the nearest stored state coordinate
        to the supplied current location.
        """
        coords, error = _parse_lat_lon()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        lat, lon = coords

        dbc.connect_db()
        states = dbc.read(STATES_COLLECT)

        if not states:
            return {
                MESSAGE: 'No state coordinates available'
            }, HTTPStatus.NOT_FOUND

        nearest = min(
            states,
            key=lambda state: haversine_km(
                lat, lon, state['Latitude'], state['Longitude']
            ),
        )
        distance = haversine_km(
            lat, lon, nearest['Latitude'], nearest['Longitude']
        )

        return {
            'state': nearest,
            'distance_km': round(distance, 2),
        }


@api.route(NEIGHBORHOOD_AT_EP)
class NeighborhoodAt(Resource):
    def get(self):
        """
        Return the neighborhood whose boundary contains lat, lon.
        """
        coords, error = _parse_lat_lon()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        neighborhood = find_neighborhood(*coords)
        if neighborhood is None:
            return {
                MESSAGE: 'No neighborhood found at that location'
            }, HTTPStatus.NOT_FOUND
        return {'neighborhood': neighborhood}


def _credentials():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
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
        Log in with JSON {username, password}; returns a JWT access token.
        """
        creds = _credentials()
        if not creds or not auth.login(*creds):
            return {MESSAGE: 'invalid credentials'}, HTTPStatus.UNAUTHORIZED
        secret = app.config.get('JWT_SECRET_KEY')
        if not secret:
            return {MESSAGE: 'Authentication unavailable'}, \
                HTTPStatus.SERVICE_UNAVAILABLE
        session.clear()
        return {
            'access_token': create_access_token(creds[0], secret),
            'token_type': 'Bearer',
            'expires_in': ACCESS_TOKEN_MINUTES * 60,
        }


@api.route(LOGOUT_EP)
class Logout(Resource):
    def post(self):
        session.clear()
        return {MESSAGE: 'logged out'}


def _parse_restaurant(data):
    """
    Validate and normalize restaurant fields from a JSON body.
    Returns (fields_dict, None) on success, or (None, error_message)
    on failure.
    """
    if not isinstance(data, dict):
        return None, 'JSON object required'
    restaurant = {}
    for field in ('name', 'city', 'cuisine', 'notes'):
        value = data.get(field, '')
        if not isinstance(value, str):
            return None, f'{field} must be text'
        value = value.strip()
        if field in ('name', 'city') and not value:
            return None, f'{field} required'
        restaurant[field] = value
    rating = data.get('rating')
    if rating is not None and (
            isinstance(rating, bool) or not isinstance(rating, (int, float))
            or not 0 <= rating <= 10):
        return None, 'rating must be a number from 0 to 10'
    restaurant['rating'] = rating

    lat, lon = data.get('lat'), data.get('lon')
    if (lat is None) != (lon is None):
        return None, 'lat and lon must be given together'
    if lat is not None:
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in (lat, lon)):
            return None, LAT_LON_BODY_NUMERIC_ERROR
        error = _lat_lon_error(lat, lon)
        if error:
            return None, error
        restaurant['location'] = geo_point(lat, lon)
    return restaurant, None


def _tag_neighborhood(restaurant):
    """
    Set restaurant['neighborhood'] to the name, borough and code of the
    neighborhood containing its location, or None.
    """
    found = None
    if restaurant.get('location'):
        lon, lat = restaurant['location']['coordinates']
        found = find_neighborhood(lat, lon)
    restaurant['neighborhood'] = None if found is None else {
        key: found.get(key) for key in ('name', 'borough', 'code')}


@api.route(RESTAURANTS_EP)
class Restaurants(Resource):
    method_decorators = [login_required]

    def get(self):
        """Return the logged-in user's saved restaurants."""
        username = g.current_user
        dbc.connect_db()
        restaurants = dbc.read(
            RESTAURANTS_COLLECT, no_id=False, filt={'user': username})
        # Best-rated first; unrated entries last.
        restaurants.sort(key=lambda r: (r.get('rating') is None,
                                        -(r.get('rating') or 0)))
        return {'restaurants': restaurants}

    def post(self):
        """Save a restaurant to the logged-in user's personal list."""
        username = g.current_user
        restaurant, error = _parse_restaurant(request.get_json(silent=True))
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST

        restaurant['user'] = username
        _tag_neighborhood(restaurant)
        dbc.connect_db()
        result = dbc.create(RESTAURANTS_COLLECT, restaurant)
        restaurant['_id'] = str(result.inserted_id)
        return {'restaurant': restaurant}, HTTPStatus.CREATED


@api.route(RESTAURANT_EP)
class Restaurant(Resource):
    method_decorators = [login_required]

    def get(self, resid):
        """Return one of the logged-in user's restaurants."""
        username = g.current_user
        try:
            obj_id = ObjectId(resid)
        except (InvalidId, TypeError):
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        dbc.connect_db()
        restaurant = dbc.read_one(
            RESTAURANTS_COLLECT, {'_id': obj_id, 'user': username})
        if restaurant is None:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND
        return {'restaurant': restaurant}

    def put(self, resid):
        """Update one of the logged-in user's restaurants."""
        username = g.current_user
        try:
            obj_id = ObjectId(resid)
        except (InvalidId, TypeError):
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        restaurant, error = _parse_restaurant(request.get_json(silent=True))
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST

        # $set only touches given fields; clear any old location.
        restaurant.setdefault('location', None)
        _tag_neighborhood(restaurant)
        dbc.connect_db()
        result = dbc.update(
            RESTAURANTS_COLLECT, {'_id': obj_id, 'user': username},
            restaurant)
        if result.matched_count == 0:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        restaurant['_id'] = resid
        restaurant['user'] = username
        return {'restaurant': restaurant}

    def delete(self, resid):
        """Delete one of the logged-in user's restaurants."""
        username = g.current_user
        try:
            obj_id = ObjectId(resid)
        except (InvalidId, TypeError):
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        dbc.connect_db()
        deleted = dbc.delete(
            RESTAURANTS_COLLECT, {'_id': obj_id, 'user': username})
        if not deleted:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND
        return {MESSAGE: 'deleted'}
