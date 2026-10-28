"""
Ranking a place: a binary search over the user's list, driven by
"which was better?" answers, then one insert at the position found.

Each user's ranking is one ordered list in `rankings`, best first,
grouped by bucket (liked, then fine, then disliked).
"""
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.jwt_auth import login_required
from server.restaurants import RESTAURANTS_COLLECT

ns = Namespace('rankings', path='/')

MESSAGE = 'Message'
RANK_SESSIONS_EP = '/rank-sessions'
RANK_ANSWER_EP = '/rank-sessions/<string:session_id>/answer'
RANKINGS_COLLECT = 'rankings'
RANK_SESSIONS_COLLECT = 'rank_sessions'
COMPARISONS_COLLECT = 'comparisons'

BUCKETS = ('liked', 'fine', 'disliked')  # best first
BETTER, WORSE, SAME = 'better', 'worse', 'same'
ANSWERS = (BETTER, WORSE, SAME)
SESSION_MINUTES = 15

SESSION_NOT_FOUND = 'Ranking session not found or expired'


def bucket_bounds(ordered, bucket):
    """
    Return (lo, hi), the slice of ordered that holds bucket. Buckets are
    contiguous and best first, so lo counts entries in better buckets.
    """
    rank = BUCKETS.index(bucket)
    lo = sum(BUCKETS.index(entry['bucket']) < rank for entry in ordered)
    hi = lo + sum(entry['bucket'] == bucket for entry in ordered)
    return lo, hi


def narrow(lo, hi, answer):
    """
    The new place can go anywhere in positions lo..hi; it was just
    compared with the place at mid. Return the narrowed (lo, hi).
    """
    mid = (lo + hi) // 2
    if answer == BETTER:
        return lo, mid
    if answer == WORSE:
        return mid + 1, hi
    return mid, mid  # too close to call: insert right above it


def _now():
    return datetime.now(timezone.utc)


def _load_ordered(username):
    ranking = dbc.read_one(RANKINGS_COLLECT, {'_id': username})
    return ranking['ordered'] if ranking else []


def _comparison(session_id, ordered, lo, hi):
    """Return the response asking the user to compare with mid."""
    resid = ordered[(lo + hi) // 2]['restaurant_id']
    return {
        'done': False,
        'session_id': session_id,
        'compare': dbc.read_one(RESTAURANTS_COLLECT, {'_id': ObjectId(resid)}),
    }


def _save(username, resid, bucket, position, pairs):
    """
    Insert the place into the user's list at position and record every
    answered pair as a comparison.
    """
    now = _now()
    entry = {'restaurant_id': resid, 'bucket': bucket, 'ranked_at': now}
    dbc.update_raw(
        RANKINGS_COLLECT, {'_id': username},
        {'$push': {'ordered': {'$each': [entry], '$position': position}},
         '$inc': {'version': 1}},
        upsert=True)
    for winner, loser in pairs:
        dbc.create(COMPARISONS_COLLECT, {
            'user': username, 'winner_id': winner, 'loser_id': loser,
            'created_at': now})
    return {'done': True, 'position': position}


@ns.route(RANK_SESSIONS_EP)
class RankSessions(Resource):
    method_decorators = [login_required]

    def post(self):
        """
        Start ranking one of your restaurants from JSON
        {restaurant_id, bucket}. Returns the first place to compare
        with, or the final position if the bucket is empty.
        """
        username = g.current_user
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get('bucket') not in BUCKETS:
            return {MESSAGE: 'bucket must be liked, fine or disliked'}, \
                HTTPStatus.BAD_REQUEST
        bucket = data['bucket']
        try:
            resid = str(ObjectId(data.get('restaurant_id')))
        except (InvalidId, TypeError):
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND

        dbc.connect_db()
        restaurant = dbc.read_one(
            RESTAURANTS_COLLECT, {'_id': ObjectId(resid), 'user': username})
        if restaurant is None:
            return {MESSAGE: 'Restaurant not found'}, HTTPStatus.NOT_FOUND
        ordered = _load_ordered(username)
        if any(entry['restaurant_id'] == resid for entry in ordered):
            return {MESSAGE: 'Restaurant already ranked'}, \
                HTTPStatus.CONFLICT

        lo, hi = bucket_bounds(ordered, bucket)
        if lo == hi:
            return _save(username, resid, bucket, lo, []), \
                HTTPStatus.CREATED

        # ponytail: sessions live in Mongo, not Redis; expired ones are
        # rejected but not removed. Add a TTL index on expires_at.
        result = dbc.create(RANK_SESSIONS_COLLECT, {
            'user': username, 'restaurant_id': resid, 'bucket': bucket,
            'lo': lo, 'hi': hi, 'pairs': [],
            'expires_at': _now() + timedelta(minutes=SESSION_MINUTES)})
        session_id = str(result.inserted_id)
        return _comparison(session_id, ordered, lo, hi), HTTPStatus.CREATED


@ns.route(RANK_ANSWER_EP)
class RankAnswer(Resource):
    method_decorators = [login_required]

    def post(self, session_id):
        """
        Answer the current comparison with JSON {answer}: better, worse
        or same, for the new place against the one shown. Returns the
        next place to compare with, or the final position.
        """
        username = g.current_user
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get('answer') not in ANSWERS:
            return {MESSAGE: 'answer must be better, worse or same'}, \
                HTTPStatus.BAD_REQUEST
        answer = data['answer']
        try:
            obj_id = ObjectId(session_id)
        except (InvalidId, TypeError):
            return {MESSAGE: SESSION_NOT_FOUND}, HTTPStatus.NOT_FOUND

        dbc.connect_db()
        session = dbc.read_one(
            RANK_SESSIONS_COLLECT, {'_id': obj_id, 'user': username})
        # Mongo hands datetimes back without a timezone; they are UTC.
        if session is None or session['expires_at'].replace(
                tzinfo=timezone.utc) < _now():
            return {MESSAGE: SESSION_NOT_FOUND}, HTTPStatus.NOT_FOUND

        ordered = _load_ordered(username)
        lo, hi, pairs = session['lo'], session['hi'], session['pairs']
        resid = session['restaurant_id']
        compared = ordered[(lo + hi) // 2]['restaurant_id']
        if answer == BETTER:
            pairs.append([resid, compared])
        elif answer == WORSE:
            pairs.append([compared, resid])

        lo, hi = narrow(lo, hi, answer)
        if lo == hi:
            dbc.delete(RANK_SESSIONS_COLLECT, {'_id': obj_id})
            return _save(username, resid, session['bucket'], lo, pairs)
        dbc.update(RANK_SESSIONS_COLLECT, {'_id': obj_id},
                   {'lo': lo, 'hi': hi, 'pairs': pairs})
        return _comparison(session_id, ordered, lo, hi)
