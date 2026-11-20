"""
Follows: logged-in users follow and unfollow each other. Each follow is
one document in the follows collection, so it can carry its own timestamp.
"""
from datetime import datetime, timezone
from http import HTTPStatus

from flask import g
from flask_restx import Namespace, Resource

import data.db_connect as dbc
from security.auth import USERNAME, USERS
from security.jwt_auth import login_required

ns = Namespace('follows', path='/')

MESSAGE = 'Message'
FOLLOW_EP = '/users/<string:username>/follow'
FOLLOWERS_EP = '/users/<string:username>/followers'
FOLLOWING_EP = '/users/<string:username>/following'
FOLLOWS_COLLECT = 'follows'
FOLLOWER = 'follower'
FOLLOWEE = 'followee'
CREATED_AT = 'created_at'

USER_NOT_FOUND = 'User not found'


def _user_exists(username):
    return dbc.read_one(USERS, {USERNAME: username}) is not None


def _usernames(field, filt):
    """Return the sorted usernames stored in field of matching follows."""
    docs = dbc.read(FOLLOWS_COLLECT, filt=filt, projection={field: 1})
    return sorted(doc[field] for doc in docs)


def following_usernames(username):
    """Return the usernames that username follows."""
    return _usernames(FOLLOWEE, {FOLLOWER: username})


@ns.route(FOLLOW_EP)
class Follow(Resource):
    method_decorators = [login_required]

    def post(self, username):
        """Follow a user. Following someone twice is fine."""
        if username == g.current_user:
            return {MESSAGE: 'You cannot follow yourself'}, \
                HTTPStatus.BAD_REQUEST
        if not _user_exists(username):
            return {MESSAGE: USER_NOT_FOUND}, HTTPStatus.NOT_FOUND
        # Upsert so a repeat follow keeps the original timestamp.
        dbc.update_raw(
            FOLLOWS_COLLECT,
            {FOLLOWER: g.current_user, FOLLOWEE: username},
            {'$setOnInsert': {CREATED_AT: datetime.now(timezone.utc)}},
            upsert=True,
        )
        return {MESSAGE: f'Following {username}'}

    def delete(self, username):
        """Unfollow a user. Unfollowing someone you don't follow is fine."""
        dbc.delete(FOLLOWS_COLLECT,
                   {FOLLOWER: g.current_user, FOLLOWEE: username})
        return {MESSAGE: f'Unfollowed {username}'}


@ns.route(FOLLOWERS_EP)
class Followers(Resource):
    method_decorators = [login_required]

    def get(self, username):
        """List the users who follow a user."""
        if not _user_exists(username):
            return {MESSAGE: USER_NOT_FOUND}, HTTPStatus.NOT_FOUND
        return {'followers': _usernames(FOLLOWER, {FOLLOWEE: username})}


@ns.route(FOLLOWING_EP)
class Following(Resource):
    method_decorators = [login_required]

    def get(self, username):
        """List the users a user follows."""
        if not _user_exists(username):
            return {MESSAGE: USER_NOT_FOUND}, HTTPStatus.NOT_FOUND
        return {'following': following_usernames(username)}
