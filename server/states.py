"""
State lookups: all states, one by abbreviation, and the nearest to a point.
"""
from http import HTTPStatus
from math import atan2, cos, radians, sin, sqrt

from flask_restx import Namespace, Resource

import data.db_connect as dbc
from server.neighborhoods import parse_lat_lon

ns = Namespace('states', path='/')

MESSAGE = 'Message'
STATES_EP = '/states'
STATES_RESP = 'states'
STATES_COLLECT = 'states'


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


@ns.route(STATES_EP)
class States(Resource):
    def get(self):
        """
        Return all states loaded by states/load.py.
        """
        dbc.connect_db()
        return {STATES_RESP: dbc.read(STATES_COLLECT)}


@ns.route('/states/<string:abbrev>')
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


@ns.route('/states/nearest')
class NearestState(Resource):
    def get(self):
        """
        Return the nearest stored state coordinate
        to the supplied current location.
        """
        coords, error = parse_lat_lon()
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
