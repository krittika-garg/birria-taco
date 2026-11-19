"""Ranking by comparison, end to end against real MongoDB."""
from datetime import datetime, timedelta, timezone

from bson import ObjectId

import server.rankings as rk


def save(client, name):
    response = client.post('/restaurants', json={'name': name,
                                                 'city': 'New York'})
    return response.get_json()['restaurant']['_id']


def start(client, resid, bucket='liked'):
    response = client.post('/rank-sessions', json={
        'restaurant_id': resid, 'bucket': bucket})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def answer(client, session_id, reply):
    return client.post(f'/rank-sessions/{session_id}/answer',
                       json={'answer': reply})


def ranked_ids(client):
    return [entry['restaurant_id'] for entry in
            client.get('/rankings').get_json()['rankings']]


def test_full_ranking_flow(login, db):
    bob = login('bob')
    a, b, c = save(bob, 'A'), save(bob, 'B'), save(bob, 'C')

    # Empty bucket: saved straight away.
    assert start(bob, a) == {'done': True, 'position': 0}

    # B vs A: worse, so B goes below A.
    first = start(bob, b)
    assert first['compare']['_id'] == a
    assert answer(bob, first['session_id'], 'worse').get_json() == {
        'done': True, 'position': 1}

    # C vs B (the middle): better; then C vs A: worse. C lands between.
    session = start(bob, c)
    assert session['compare']['_id'] == b
    next_step = answer(bob, session['session_id'], 'better').get_json()
    assert next_step['compare']['_id'] == a
    assert answer(bob, session['session_id'], 'worse').get_json() == {
        'done': True, 'position': 1}

    assert ranked_ids(bob) == [a, c, b]
    rankings = bob.get('/rankings').get_json()['rankings']
    scores = [entry['score'] for entry in rankings]
    assert scores == sorted(scores, reverse=True)
    assert all(6.7 <= score <= 10 for score in scores)
    datetime.fromisoformat(rankings[0]['ranked_at'])

    stored = db['comparisons'].find({}, {'_id': 0, 'user': 1,
                                         'winner_id': 1, 'loser_id': 1})
    assert sorted((d['winner_id'], d['loser_id']) for d in stored) == sorted(
        [(a, b), (c, b), (a, c)])
    # Finished sessions are removed.
    assert db['rank_sessions'].count_documents({}) == 0


def test_buckets_order_the_list(login):
    bob = login('bob')
    meh, great, awful = save(bob, 'Meh'), save(bob, 'Great'), \
        save(bob, 'Awful')
    start(bob, meh, 'fine')
    start(bob, awful, 'disliked')
    # Liked is empty, so Great goes straight to the top.
    assert start(bob, great, 'liked') == {'done': True, 'position': 0}
    assert ranked_ids(bob) == [great, meh, awful]


def test_cannot_rank_twice_or_rank_others(login):
    bob, alice = login('bob'), login('alice')
    mine = save(bob, 'Mine')
    start(bob, mine)
    again = bob.post('/rank-sessions', json={'restaurant_id': mine,
                                             'bucket': 'fine'})
    assert again.status_code == 409
    theirs = alice.post('/rank-sessions', json={'restaurant_id': mine,
                                                'bucket': 'liked'})
    assert theirs.status_code == 404


def test_list_changed_mid_session_conflicts(login):
    bob = login('bob')
    a, b, c = save(bob, 'A'), save(bob, 'B'), save(bob, 'C')
    start(bob, a)
    slow = start(bob, b)            # compares against A at version 1
    fast = start(bob, c)
    answer(bob, fast['session_id'], 'better')   # C saved: version 2

    response = answer(bob, slow['session_id'], 'better')
    assert response.status_code == 409
    assert ranked_ids(bob) == [c, a]


def test_stale_version_write_is_refused_by_mongo(login, db):
    # The guard in _save depends on Mongo refusing an upsert whose filter
    # misses only because of the version: it tries to insert a second doc
    # with the same _id and raises DuplicateKeyError.
    bob = login('bob')
    a, b = save(bob, 'A'), save(bob, 'B')
    start(bob, a)
    assert rk._save('bob', b, 'liked', 0, [], version=0) is None
    assert [e['restaurant_id'] for e in db['rankings'].find_one(
        {'_id': 'bob'})['ordered']] == [a]


def test_expired_session_is_gone(login, db):
    bob = login('bob')
    a, b = save(bob, 'A'), save(bob, 'B')
    start(bob, a)
    session = start(bob, b)
    db['rank_sessions'].update_one(
        {'_id': ObjectId(session['session_id'])},
        {'$set': {'expires_at': datetime.now(timezone.utc)
                  - timedelta(minutes=1)}})
    assert answer(bob, session['session_id'], 'better').status_code == 404


def test_other_users_session_is_hidden(login):
    bob, alice = login('bob'), login('alice')
    a, b = save(bob, 'A'), save(bob, 'B')
    start(bob, a)
    session = start(bob, b)
    assert answer(alice, session['session_id'], 'better').status_code == 404
