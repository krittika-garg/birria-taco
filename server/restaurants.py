"""
The logged-in user's personal restaurant list.
"""
from http import HTTPStatus
from math import isfinite

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.jwt_auth import login_required
from places.load import geo_point
from server.neighborhoods import (
    LAT_LON_BODY_NUMERIC_ERROR, find_neighborhood, lat_lon_error,
    parse_lat_lon)
from server.states import haversine_km

ns = Namespace('restaurants', path='/')

MESSAGE = 'Message'
RESTAURANTS_EP = '/restaurants'
RESTAURANT_EP = '/restaurants/<string:resid>'
RESTAURANTS_NEARBY_EP = '/restaurants/nearby'
RESTAURANTS_COLLECT = 'restaurants'
STATUSES = ('visited', 'want_to_try')
STATUS_ERROR = 'status must be visited or want_to_try'

EARTH_RADIUS_KM = 6371
DEFAULT_RADIUS_KM = 2
MAX_RADIUS_KM = 50
RADIUS_ERROR = f'radius_km must be greater than 0 and at most {MAX_RADIUS_KM}'


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
    status = data.get('status', 'visited')
    if status not in STATUSES:
        return None, STATUS_ERROR
    restaurant['status'] = status
    rating = data.get('rating')
    if rating is not None and (
            isinstance(rating, bool) or not isinstance(rating, (int, float))
            or not 0 <= rating <= 10):
        return None, 'rating must be a number from 0 to 10'
    if status == 'want_to_try' and rating is not None:
        return None, 'want_to_try restaurants cannot have a rating'
    restaurant['rating'] = rating

    lat, lon = data.get('lat'), data.get('lon')
    if (lat is None) != (lon is None):
        return None, 'lat and lon must be given together'
    if lat is not None:
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in (lat, lon)):
            return None, LAT_LON_BODY_NUMERIC_ERROR
        error = lat_lon_error(lat, lon)
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


@ns.route(RESTAURANTS_EP)
class Restaurants(Resource):
    method_decorators = [login_required]

    @ns.doc(params={
        'q': 'Case-insensitive text contained in the restaurant name',
        'cuisine': 'Case-insensitive exact cuisine',
        'min_rating': 'Minimum rating, from 0 to 10 (inclusive)',
        'status': 'visited or want_to_try; omitted returns both',
    })
    def get(self):
        """Return the logged-in user's saved restaurants."""
        query = request.args.get('q', '').strip().casefold()
        cuisine = request.args.get('cuisine', '').strip().casefold()
        status = request.args.get('status')
        if status is not None and status not in STATUSES:
            return {MESSAGE: STATUS_ERROR}, HTTPStatus.BAD_REQUEST
        min_rating = None
        if 'min_rating' in request.args:
            error = {MESSAGE: 'min_rating must be a number from 0 to 10'}
            try:
                min_rating = float(request.args['min_rating'])
            except ValueError:
                return error, HTTPStatus.BAD_REQUEST
            if not isfinite(min_rating) or not 0 <= min_rating <= 10:
                return error, HTTPStatus.BAD_REQUEST
        username = g.current_user
        restaurants = dbc.read(
            RESTAURANTS_COLLECT, no_id=False, filt={'user': username})
        for restaurant in restaurants:
            restaurant.setdefault('status', 'visited')
        restaurants = [r for r in restaurants
                       if query in r.get('name', '').casefold()
                       and (status is None or r['status'] == status)
                       and (not cuisine or
                            cuisine == r.get('cuisine', '').casefold())
                       and (min_rating is None or
                            (r.get('rating') is not None and
                             r['rating'] >= min_rating))]
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
        result = dbc.create(RESTAURANTS_COLLECT, restaurant)
        restaurant['_id'] = str(result.inserted_id)
        return {'restaurant': restaurant}, HTTPStatus.CREATED


def _parse_radius_km():
    """
    Read the optional radius_km query parameter.
    Returns (radius_km, None) on success, or (None, error_message)
    on failure.
    """
    try:
        radius_km = float(request.args.get('radius_km', DEFAULT_RADIUS_KM))
    except (TypeError, ValueError):
        return None, RADIUS_ERROR
    if not isfinite(radius_km) or not 0 < radius_km <= MAX_RADIUS_KM:
        return None, RADIUS_ERROR
    return radius_km, None


@ns.route(RESTAURANTS_NEARBY_EP)
class RestaurantsNearby(Resource):
    method_decorators = [login_required]

    def get(self):
        """
        Return the logged-in user's saved restaurants within radius_km
        (default 2) of lat, lon, closest first.
        """
        coords, error = parse_lat_lon()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        radius_km, error = _parse_radius_km()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        lat, lon = coords

        restaurants = dbc.read(RESTAURANTS_COLLECT, no_id=False, filt={
            'user': g.current_user,
            'location': {'$geoWithin': {'$centerSphere': [
                [lon, lat], radius_km / EARTH_RADIUS_KM]}},
        })
        for restaurant in restaurants:
            res_lon, res_lat = restaurant['location']['coordinates']
            restaurant.setdefault('status', 'visited')
            restaurant['distance_km'] = round(
                haversine_km(lat, lon, res_lat, res_lon), 2)
        restaurants.sort(key=lambda r: r['distance_km'])
        return {'restaurants': restaurants}


@ns.route(RESTAURANT_EP)
class Restaurant(Resource):
    method_decorators = [login_required]

    def get(self, resid):
        """Return one of the logged-in user's restaurants."""
        username = g.current_user
        try:
            obj_id = ObjectId(resid)
        except (InvalidId, TypeError):
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        restaurant = dbc.read_one(
            RESTAURANTS_COLLECT, {'_id': obj_id, 'user': username})
        if restaurant is None:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND
        restaurant.setdefault('status', 'visited')
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

        deleted = dbc.delete(
            RESTAURANTS_COLLECT, {'_id': obj_id, 'user': username})
        if not deleted:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND
        return {MESSAGE: 'deleted'}
