"""Recent restaurant rankings from the users you follow."""

from flask_restx import Namespace

ns = Namespace('feed', path='/')

FEED_EP = '/feed'
FEED_LIMIT = 20
