"""
The logged-in user's personal restaurant list.
"""
from http import HTTPStatus

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.jwt_auth import login_required
from places.load import geo_point
from server.neighborhoods import (
    LAT_LON_BODY_NUMERIC_ERROR, find_neighborhood, lat_lon_error)

ns = Namespace('restaurants', path='/')

MESSAGE = 'Message'
RESTAURANTS_EP = '/restaurants'
RESTAURANT_EP = '/restaurants/<string:resid>'
RESTAURANTS_COLLECT = 'restaurants'


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
