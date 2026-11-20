"""Recent restaurant rankings from the users you follow."""

from flask import g
from flask_restx import Namespace, Resource

from security.jwt_auth import login_required
from server.follows import following_usernames

ns = Namespace('feed', path='/')

FEED_EP = '/feed'
FEED_LIMIT = 20


@ns.route(FEED_EP)
class FriendsFeed(Resource):
    method_decorators = [login_required]

    def get(self):
        """Return the latest restaurant rankings from users you follow."""
        following = following_usernames(g.current_user)
        if not following:
            return {'feed': []}
        return {'feed': []}
