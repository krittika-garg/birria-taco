"""
Neighborhood lookup, plus the lat/lon helpers other features share.
"""
from http import HTTPStatus
from math import isfinite

from flask import request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from places.load import NEIGHBORHOOD, PLACES_COLLECT, geo_point

ns = Namespace('neighborhoods', path='/')

MESSAGE = 'Message'
NEIGHBORHOOD_AT_EP = '/neighborhoods/at'

LAT_LON_NUMERIC_ERROR = 'Provide numeric lat and lon query parameters'
LAT_LON_BODY_NUMERIC_ERROR = 'lat and lon must be numbers'
LAT_LON_RANGE_ERROR = ('lat must be between -90 and 90; '
                       'lon must be between -180 and 180')


def lat_lon_error(lat, lon):
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


def parse_lat_lon():
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

    error = lat_lon_error(lat, lon)
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


@ns.route(NEIGHBORHOOD_AT_EP)
class NeighborhoodAt(Resource):
    def get(self):
        """
        Return the neighborhood whose boundary contains lat, lon.
        """
        coords, error = parse_lat_lon()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        neighborhood = find_neighborhood(*coords)
        if neighborhood is None:
            return {
                MESSAGE: 'No neighborhood found at that location'
            }, HTTPStatus.NOT_FOUND
        return {'neighborhood': neighborhood}
