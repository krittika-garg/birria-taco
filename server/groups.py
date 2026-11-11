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


@ns.route(GROUPS_EP)
class Groups(Resource):
    method_decorators = [login_required]

    def get(self):
        """Return the live groups you are a member of, newest first."""
        groups = dbc.read(GROUPS_COLLECT, no_id=False,
                          filt={'members': g.current_user})
        # The TTL index removes expired groups lazily, so check here too.
        live = [group for group in map(_live, groups) if group]
        live.sort(key=lambda group: group['expires_at'], reverse=True)
        return {'groups': live}

    def post(self):
        """
        Start a group with you as host and only member. Share
        invite_token so friends can join through /groups/join/<token>.
        """
        dbc.create_index(
            GROUPS_COLLECT, [('expires_at', 1)], expireAfterSeconds=0)
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


@ns.route('/groups/<string:group_id>/leave')
class LeaveGroup(Resource):
    method_decorators = [login_required]

    def post(self, group_id):
        """Leave a live group; hosts must remain."""
        try:
            obj_id = ObjectId(group_id)
        except (InvalidId, TypeError):
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND

        group = dbc.read_one(
            GROUPS_COLLECT, {'_id': obj_id, 'members': g.current_user})
        if not group or not _live(group):
            return {MESSAGE: GROUP_NOT_FOUND}, HTTPStatus.NOT_FOUND
        if group['host'] == g.current_user:
            return {MESSAGE: 'Host cannot leave the group'}, \
                HTTPStatus.CONFLICT

        dbc.update_raw(
            GROUPS_COLLECT, {'_id': obj_id},
            {'$pull': {'members': g.current_user}})
        return {MESSAGE: 'Left group'}
