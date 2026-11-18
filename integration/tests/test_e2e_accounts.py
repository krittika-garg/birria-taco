"""Accounts and tokens, end to end against real MongoDB."""
from integration.tests.support import PASSWORD

CREDS = {'username': 'bob', 'password': PASSWORD}


def test_register_login_and_use_token(anon, db):
    assert anon.post('/register', json=CREDS).status_code == 201
    response = anon.post('/login', json=CREDS)
    assert response.status_code == 200
    body = response.get_json()
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 900

    response = anon.get('/restaurants', headers={
        'Authorization': f"Bearer {body['access_token']}"})
    assert response.status_code == 200
    assert response.get_json() == {'restaurants': []}


def test_password_is_stored_hashed(anon, db):
    anon.post('/register', json=CREDS)
    user = db['users'].find_one({'username': 'bob'})
    assert PASSWORD not in str(user)
    assert user['password_hash'] != PASSWORD


def test_duplicate_username_conflicts(anon, db):
    # Relies on the unique index initialize_indexes creates.
    assert anon.post('/register', json=CREDS).status_code == 201
    response = anon.post('/register', json={**CREDS, 'password': 'other'})
    assert response.status_code == 409
    assert db['users'].count_documents({'username': 'bob'}) == 1


def test_bad_logins_look_the_same(anon, db):
    anon.post('/register', json=CREDS)
    wrong_password = anon.post('/login', json={**CREDS, 'password': 'nope'})
    unknown_user = anon.post('/login', json={**CREDS, 'username': 'eve'})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.get_json() == unknown_user.get_json()


def test_operator_in_username_is_rejected(anon, db):
    anon.post('/register', json=CREDS)
    response = anon.post('/login', json={
        'username': {'$ne': None}, 'password': PASSWORD})
    assert response.status_code == 401


def test_refresh_rotates_and_works_once(login, anon):
    bob = login('bob')
    first = bob.refresh_token

    response = anon.post('/refresh', json={'refresh_token': first})
    assert response.status_code == 200
    second = response.get_json()['refresh_token']
    assert second != first

    # The first token was used up; the new one still works.
    assert anon.post('/refresh', json={
        'refresh_token': first}).status_code == 401
    assert anon.post('/refresh', json={
        'refresh_token': second}).status_code == 200


def test_logout_revokes_refresh_token(login, anon, db):
    bob = login('bob')
    response = anon.post('/logout', json={'refresh_token': bob.refresh_token})
    assert response.status_code == 200
    assert db['refresh_tokens'].count_documents({}) == 0
    assert anon.post('/refresh', json={
        'refresh_token': bob.refresh_token}).status_code == 401


def test_only_token_hashes_are_stored(login, db):
    bob = login('bob')
    stored = db['refresh_tokens'].find_one({'username': 'bob'})
    assert bob.refresh_token not in str(stored)


def test_startup_indexes(db):
    users = db['users'].index_information()
    assert any(info.get('unique') and info['key'] == [('username', 1)]
               for info in users.values())
    for collection in ('refresh_tokens', 'groups', 'rank_sessions'):
        indexes = db[collection].index_information().values()
        assert any(info['key'] == [('expires_at', 1)]
                   and info.get('expireAfterSeconds') == 0
                   for info in indexes), collection
