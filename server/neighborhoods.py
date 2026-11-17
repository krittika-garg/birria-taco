"""
Neighborhood lookup and leaderboards, plus the lat/lon helpers other
features share.
"""
from collections import Counter
from http import HTTPStatus
from math import isfinite

from flask import request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from places.load import NEIGHBORHOOD, PLACES_COLLECT, geo_point

ns = Namespace('neighborhoods', path='/')

MESSAGE = 'Message'
NEIGHBORHOODS_EP = '/neighborhoods'
NEIGHBORHOOD_AT_EP = '/neighborhoods/at'
LEADERBOARD_EP = '/neighborhoods/<string:code>/leaderboard'

NEIGHBORHOOD_NOT_FOUND = 'Neighborhood not found'

# Bayesian prior weight: each restaurant's score starts as if it had this
# many ratings at the neighborhood mean, so one rating can't top the board.
LEADERBOARD_PRIOR = 3
DEFAULT_LEADERBOARD_LIMIT = 10
MAX_LEADERBOARD_LIMIT = 50
LIMIT_ERROR = f'limit must be an integer from 1 to {MAX_LEADERBOARD_LIMIT}'

BOROUGHS = ('Bronx', 'Brooklyn', 'Manhattan', 'Queens', 'Staten Island')
BOROUGH_ERROR = 'borough must be one of: ' + ', '.join(BOROUGHS)

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


def parse_borough(text):
    """
    Return the canonical borough name for text, ignoring case and extra
    whitespace, or None if it isn't a borough.
    """
    wanted = ' '.join(text.split()).casefold()
    for borough in BOROUGHS:
        if borough.casefold() == wanted:
            return borough
    return None


def find_neighborhood(lat, lon):
    """
    Return the neighborhood whose boundary contains lat, lon, without
    _id and boundary, or None if no neighborhood contains it.
    """
    neighborhood = dbc.read_one(PLACES_COLLECT, {
        'type': NEIGHBORHOOD,
        'boundary': {'$geoIntersects': {'$geometry': geo_point(lat, lon)}},
    })
    if neighborhood is None:
        return None
    neighborhood.pop('_id', None)
    neighborhood.pop('boundary', None)
    return neighborhood


def collapse_whitespace(text):
    """Strip text and collapse each run of whitespace to one space."""
    return ' '.join(text.split())


def name_order(name):
    """
    Sort key for names: case-insensitive first; among names that differ
    only in case, lowercase letters win ('Taqueria' before 'TAQUERIA').
    """
    return name.lower(), name.swapcase()


def leaderboard(entries, prior=LEADERBOARD_PRIOR):
    """
    Rank restaurants from a list of {'name', 'rating'} entries.

    Entries are grouped by name, ignoring case and whitespace. Each group
    gets a Bayesian average,
        score = (prior * m + sum_of_ratings) / (prior + count),
    where m is the mean of all ratings in entries. Each group is shown
    under its most common spelling, ties broken by name_order.

    Returns a list of {'name', 'score', 'average', 'ratings'} (ratings is
    the count), with score and average rounded to 2 decimals, sorted by
    score desc, then ratings desc, then name_order.
    """
    if not entries:
        return []
    groups = {}
    for entry in entries:
        spelling = collapse_whitespace(entry['name'])
        groups.setdefault(spelling.lower(), []).append(
            (spelling, entry['rating']))
    mean = sum(entry['rating'] for entry in entries) / len(entries)

    board = []
    for group in groups.values():
        spellings = Counter(spelling for spelling, _ in group)
        name = min(spellings,
                   key=lambda s: (-spellings[s], *name_order(s)))
        total = sum(rating for _, rating in group)
        count = len(group)
        board.append({
            'name': name,
            'score': round((prior * mean + total) / (prior + count), 2),
            'average': round(total / count, 2),
            'ratings': count,
        })
    board.sort(key=lambda r: (-r['score'], -r['ratings'],
                              *name_order(r['name'])))
    return board


def parse_limit():
    """
    Read limit from the query string, defaulting to
    DEFAULT_LEADERBOARD_LIMIT.
    Returns (limit, None) on success, or (None, LIMIT_ERROR) on failure.
    """
    raw = request.args.get('limit')
    if raw is None:
        return DEFAULT_LEADERBOARD_LIMIT, None
    try:
        limit = int(raw)
    except ValueError:
        return None, LIMIT_ERROR
    if not 1 <= limit <= MAX_LEADERBOARD_LIMIT:
        return None, LIMIT_ERROR
    return limit, None


@ns.route(NEIGHBORHOODS_EP)
class Neighborhoods(Resource):
    def get(self):
        """
        List NYC neighborhoods sorted by name, optionally in one borough.
        """
        filt = {'type': NEIGHBORHOOD}
        if 'borough' in request.args:
            borough = parse_borough(request.args['borough'])
            if borough is None:
                return {MESSAGE: BOROUGH_ERROR}, HTTPStatus.BAD_REQUEST
            filt['borough'] = borough
        neighborhoods = dbc.read(
            PLACES_COLLECT, filt=filt, projection={'boundary': 0})
        neighborhoods.sort(key=lambda hood: hood['name'])
        return {'neighborhoods': neighborhoods}


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


@ns.route(LEADERBOARD_EP)
class NeighborhoodLeaderboard(Resource):
    def get(self, code):
        """
        Return the best-rated restaurants in one neighborhood, combining
        every user's ratings. Optional limit (1-50, default 10).
        """
        # Imported here, not at the top: server.restaurants imports this
        # module at load time, so a top-level import would be circular.
        from server.restaurants import RESTAURANTS_COLLECT

        limit, error = parse_limit()
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        code = code.upper()
        neighborhood = dbc.read_one(
            PLACES_COLLECT, {'type': NEIGHBORHOOD, 'code': code})
        if neighborhood is None:
            return {MESSAGE: NEIGHBORHOOD_NOT_FOUND}, HTTPStatus.NOT_FOUND
        entries = dbc.read(
            RESTAURANTS_COLLECT,
            filt={'neighborhood.code': code, 'rating': {'$ne': None}},
            projection={'name': 1, 'rating': 1})
        return {
            'neighborhood': {
                'name': neighborhood['name'],
                'borough': neighborhood['borough'],
                'code': neighborhood['code'],
            },
            'restaurants': leaderboard(entries)[:limit],
        }
