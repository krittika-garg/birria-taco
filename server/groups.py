"""
Group mode: a host starts a group and shares an invite link; anyone
logged in who opens the link before it expires joins as a member.
"""
import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from bson import ObjectId
from bson.errors import InvalidId
from flask import g
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.jwt_auth import login_required

ns = Namespace('groups', path='/')

MESSAGE = 'Message'
GROUPS_EP = '/groups'
GROUP_EP = '/groups/<string:group_id>'
JOIN_EP = '/groups/join/<string:token>'
GROUPS_COLLECT = 'groups'
GROUP_HOURS = 2

GROUP_NOT_FOUND = 'Group not found or expired'


def _now():
    return datetime.now(timezone.utc)


def _live(group):
    """Return group as JSON if it hasn't expired, else None."""
    # Mongo hands datetimes back without a timezone; they are UTC.
    expires_at = group['expires_at'].replace(tzinfo=timezone.utc)
    if expires_at < _now():
        return None
    return {**group, 'expires_at': expires_at.isoformat()}


# ponytail: expired groups are refused but never removed. Add a TTL
# index on expires_at when the collection grows.
@ns.route(GROUPS_EP)
class Groups(Resource):
    method_decorators = [login_required]

    def post(self):
        """
        Start a group with you as host and only member. Share
        invite_token so friends can join through /groups/join/<token>.
        """
        group = {
            'host': g.current_user,
            'members': [g.current_user],
            'invite_token': secrets.token_urlsafe(16),
            'expires_at': _now() + timedelta(hours=GROUP_HOURS),
        }
        result = dbc.create(GROUPS_COLLECT, group)
        group['_id'] = str(result.inserted_id)
        return {'group': _live(group)}, HTTPStatus.CREATED


@ns.route(GROUP_EP)
class Group(Resource):
    method_decorators = [login_required]

    def get(self, group_id):
        """Return a group you are a member of."""
        try:
            obj_id = ObjectId(group_id)
        except (InvalidId, TypeError):
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        # Non-members get the same 404, so ids can't be probed.
        group = dbc.read_one(
            GROUPS_COLLECT, {'_id': obj_id, 'members': g.current_user})
        live = group and _live(group)
        if not live:
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        return {'group': live}


@ns.route(JOIN_EP)
class JoinGroup(Resource):
    method_decorators = [login_required]

    def post(self, token):
        """Join the group behind an invite link. Joining twice is fine."""
        group = dbc.read_one(GROUPS_COLLECT, {'invite_token': token})
        if not group or not _live(group):
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        # $addToSet so two people joining at once can't drop each other.
        dbc.update_raw(GROUPS_COLLECT, {'_id': ObjectId(group['_id'])},
                       {'$addToSet': {'members': g.current_user}})
        if g.current_user not in group['members']:
            group['members'].append(g.current_user)
        return {'group': _live(group)}
