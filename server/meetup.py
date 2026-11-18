"""
Group meetups: members share where they are, and the group gets a fair
meeting point that keeps the longest trip as short as possible.
"""
from http import HTTPStatus
from itertools import combinations
from math import cos, radians

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from places.load import geo_point
from security.jwt_auth import login_required
from server.groups import GROUP_NOT_FOUND, GROUPS_COLLECT, _live
from server.neighborhoods import LAT_LON_BODY_NUMERIC_ERROR, lat_lon_error
from server.states import haversine_km

ns = Namespace('meetup', path='/')

MESSAGE = 'Message'
LOCATION_EP = '/groups/<string:group_id>/location'
MIDPOINT_EP = '/groups/<string:group_id>/midpoint'

NO_LOCATIONS = 'No member has shared a location yet'

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_AT_EQUATOR = 111.320
FIT_TOLERANCE_KM = 1e-9


def _circle_from_diameter(a, b):
    """Return (center, radius) of the circle with segment ab as diameter."""
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return center, _dist(center, a)


def _circumcircle(a, b, c):
    """Return (center, radius) through a, b, c, or None if collinear."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if d == 0:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    center = ((a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d,
              (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d)
    return center, _dist(center, a)


def _dist(p, q):
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def fair_midpoint(points):
    """
    Return the (lat, lon) that minimizes the longest distance from any of
    points, a non-empty list of (lat, lon): the center of their smallest
    enclosing circle.

    Why not the plain average? The average minimizes the *sum of squared*
    distances, so it gets pulled toward wherever most people are. With
    three friends downtown and one across town, the average lands near
    downtown and the lone friend has by far the longest trip. The center
    of the smallest enclosing circle depends only on the people farthest
    out, so nobody travels more than they must: here it sits halfway
    between the lone friend and the farthest downtown friend.

    Points are projected onto a flat km plane centered on their mean,
    which is accurate at city scale (it ignores the antimeridian). The
    circle is found exactly by brute force: the smallest circle through
    some pair (as a diameter) or triple of points that contains them all.
    That is O(n^4), fine for a group of friends.
    """
    unique = list(dict.fromkeys((float(lat), float(lon))
                                for lat, lon in points))
    if len(unique) == 1:
        return unique[0]

    mean_lat = sum(lat for lat, _ in unique) / len(unique)
    mean_lon = sum(lon for _, lon in unique) / len(unique)
    km_per_deg_lon = KM_PER_DEG_LON_AT_EQUATOR * cos(radians(mean_lat))
    # Centering on the mean keeps coordinates small, so rounding stays
    # far below FIT_TOLERANCE_KM.
    plane = [((lon - mean_lon) * km_per_deg_lon,
              (lat - mean_lat) * KM_PER_DEG_LAT) for lat, lon in unique]

    candidates = [_circle_from_diameter(a, b)
                  for a, b in combinations(plane, 2)]
    candidates += filter(None, (_circumcircle(a, b, c)
                                for a, b, c in combinations(plane, 3)))
    best = None
    for center, radius in candidates:
        if best is not None and radius >= best[1]:
            continue
        if all(_dist(center, p) <= radius + FIT_TOLERANCE_KM
               for p in plane):
            best = (center, radius)

    (x, y), _ = best
    return mean_lat + y / KM_PER_DEG_LAT, mean_lon + x / km_per_deg_lon


def _member_group(group_id):
    """
    Return the live group group_id if the caller is a member, else None.
    Bad ids, non-members and expired groups all look the same.
    """
    try:
        obj_id = ObjectId(group_id)
    except (InvalidId, TypeError):
        return None
    group = dbc.read_one(
        GROUPS_COLLECT, {'_id': obj_id, 'members': g.current_user})
    return group and _live(group)


def _parse_location(data):
    """
    Validate {lat, lon} from a JSON body.
    Returns ((lat, lon), None) on success, or (None, error_message).
    """
    if not isinstance(data, dict):
        return None, 'JSON object required'
    lat, lon = data.get('lat'), data.get('lon')
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           for v in (lat, lon)):
        return None, LAT_LON_BODY_NUMERIC_ERROR
    error = lat_lon_error(lat, lon)
    if error:
        return None, error
    return (lat, lon), None


@ns.route(LOCATION_EP)
class GroupLocation(Resource):
    method_decorators = [login_required]

    def put(self, group_id):
        """Share (or replace) your location with a group you are in."""
        group = _member_group(group_id)
        if not group:
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        coords, error = _parse_location(request.get_json(silent=True))
        if error:
            return {MESSAGE: error}, HTTPStatus.BAD_REQUEST
        lat, lon = coords

        me = g.current_user
        # Mongo can't $pull and $push one field in a single update.
        filt = {'_id': ObjectId(group['_id'])}
        dbc.update_raw(GROUPS_COLLECT, filt,
                       {'$pull': {'locations': {'user': me}}})
        dbc.update_raw(GROUPS_COLLECT, filt, {'$push': {'locations': {
            'user': me, 'location': geo_point(lat, lon)}}})
        return {'location': {'lat': lat, 'lon': lon}}


@ns.route(MIDPOINT_EP)
class GroupMidpoint(Resource):
    method_decorators = [login_required]

    def get(self, group_id):
        """
        Return the fair meeting point for members who shared a location:
        the spot that minimizes the longest distance anyone travels.
        """
        group = _member_group(group_id)
        if not group:
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        members = set(group['members'])
        # Keyed by user, last entry wins, in case two PUTs interleaved.
        by_user = {}
        for entry in group.get('locations', []):
            if entry.get('user') in members:
                lon, lat = entry['location']['coordinates']
                by_user[entry['user']] = (lat, lon)
        if not by_user:
            return {MESSAGE: NO_LOCATIONS}, HTTPStatus.NOT_FOUND

        lat, lon = fair_midpoint(list(by_user.values()))
        lat, lon = round(lat, 6), round(lon, 6)
        max_km = max(haversine_km(lat, lon, p_lat, p_lon)
                     for p_lat, p_lon in by_user.values())
        return {
            'midpoint': {'lat': lat, 'lon': lon},
            'located': len(by_user),
            'members': len(group['members']),
            'max_km': round(max_km, 2),
        }
