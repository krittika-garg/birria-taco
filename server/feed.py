"""Recent restaurant rankings from the users you follow."""

from flask_restx import Namespace, Resource

ns = Namespace('feed', path='/')

FEED_EP = '/feed'
FEED_LIMIT = 20


@ns.route(FEED_EP)
class FriendsFeed(Resource):
    def get(self):
        """Return the latest restaurant rankings from users you follow."""
        return {'feed': []}
