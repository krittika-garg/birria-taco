"""
Group voting: each member backs one restaurant that someone in the group
has saved, and everyone sees the tally. Votes live on the group doc, so
they go away with the group when its 2 hours are up.
"""
from http import HTTPStatus

from bson import ObjectId
from bson.errors import InvalidId
from flask import g, request
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.jwt_auth import login_required
from server.groups import GROUP_NOT_FOUND, GROUPS_COLLECT
from server.meetup import _member_group
from server.restaurants import RESTAURANTS_COLLECT

ns = Namespace('votes', path='/')

MESSAGE = 'Message'
VOTE_EP = '/groups/<string:group_id>/vote'
VOTES_EP = '/groups/<string:group_id>/votes'

RESTAURANT_ID_REQUIRED = 'restaurant_id required'
RESTAURANT_NOT_IN_GROUP = 'No one in this group has saved that restaurant'


def _object_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _current_votes(group):
    """
    Return {user: restaurant_id} for members who voted. People who left
    don't count, and the last entry per user wins, in case two PUTs
    interleaved.
    """
    members = set(group['members'])
    return {v['user']: v['restaurant_id'] for v in group.get('votes', [])
            if v.get('user') in members}


@ns.route(VOTE_EP)
class GroupVote(Resource):
    method_decorators = [login_required]

    def put(self, group_id):
        """
        Vote for a restaurant saved by any group member, replacing your
        earlier vote. Body: {"restaurant_id": "..."}.
        """
        group = _member_group(group_id)
        if not group:
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        data = request.get_json(silent=True)
        resid = data.get('restaurant_id') if isinstance(data, dict) else None
        if not isinstance(resid, str) or not resid:
            return {MESSAGE: RESTAURANT_ID_REQUIRED}, HTTPStatus.BAD_REQUEST
        obj_id = _object_id(resid)
        # ponytail: restaurants are per-user docs, so two members saving
        # the same place split its votes; fixed by the shared catalog.
        if not obj_id or not dbc.read_one(RESTAURANTS_COLLECT, {
                '_id': obj_id, 'user': {'$in': group['members']}}):
            return {MESSAGE: RESTAURANT_NOT_IN_GROUP}, HTTPStatus.NOT_FOUND

        me = g.current_user
        # Same pattern as meetup locations: Mongo can't $pull and $push
        # one field in a single update.
        filt = {'_id': ObjectId(group['_id'])}
        dbc.update_raw(GROUPS_COLLECT, filt,
                       {'$pull': {'votes': {'user': me}}})
        dbc.update_raw(GROUPS_COLLECT, filt, {'$push': {'votes': {
            'user': me, 'restaurant_id': resid}}})
        return {'vote': {'restaurant_id': resid}}


@ns.route(VOTES_EP)
class GroupVotes(Resource):
    method_decorators = [login_required]

    def get(self, group_id):
        """
        Return the tally, most votes first, with your own vote. Votes for
        restaurants deleted since are dropped. Who voted for what stays
        private.
        """
        group = _member_group(group_id)
        if not group:
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        votes = _current_votes(group)
        counts = {}
        for resid in votes.values():
            counts[resid] = counts.get(resid, 0) + 1

        ids = [_object_id(r) for r in counts]
        names = {r['_id']: r['name'] for r in dbc.read(
            RESTAURANTS_COLLECT, no_id=False,
            filt={'_id': {'$in': [i for i in ids if i]}},
            projection={'name': 1})}
        tally = [{'restaurant_id': resid, 'name': names[resid],
                  'votes': n} for resid, n in counts.items()
                 if resid in names]
        tally.sort(key=lambda t: (-t['votes'], t['name']))
        my_vote = votes.get(g.current_user)
        return {
            'tally': tally,
            'my_vote': my_vote if my_vote in names else None,
            'voted': sum(t['votes'] for t in tally),
            'members': len(group['members']),
        }
