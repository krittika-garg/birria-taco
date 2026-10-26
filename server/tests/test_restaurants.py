from unittest.mock import MagicMock, patch

import pytest

import server.endpoints as ep


from security.tokens import create_access_token

TEST_JWT_SECRET = 'test-only-secret-key-at-least-32-characters'


@pytest.fixture(autouse=True)
def jwt_config(monkeypatch):
    monkeypatch.setitem(ep.app.config, 'JWT_SECRET_KEY', TEST_JWT_SECRET)


A_RESID = '507f1f77bcf86cd799439011'


@pytest.mark.parametrize('method', ['get', 'post'])
def test_login_required(method):
    response = getattr(ep.app.test_client(), method)(ep.RESTAURANTS_EP)
    assert response.status_code == 401


@pytest.mark.parametrize('method', ['put', 'delete'])
def test_edit_delete_login_required(method):
    url = ep.RESTAURANTS_EP + f'/{A_RESID}'
    response = getattr(ep.app.test_client(), method)(url)
    assert response.status_code == 401


@pytest.mark.parametrize('resid', [A_RESID, 'not-an-object-id'])
@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.update', autospec=True)
@patch('data.db_connect.delete', autospec=True)
def test_edit_delete_not_found(delete, update, connect, resid):
    update.return_value = MagicMock(matched_count=0)
    delete.return_value = 0
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    url = ep.RESTAURANTS_EP + f'/{resid}'
    response = client.put(url, json={'name': 'Tacos', 'city': 'NY'})
    assert response.status_code == 404
    assert client.delete(url).status_code == 404


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.update', autospec=True)
@patch('data.db_connect.delete', autospec=True)
def test_edit_delete_success(delete, update, connect):
    update.return_value = MagicMock(matched_count=1)
    delete.return_value = 1
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    url = ep.RESTAURANTS_EP + f'/{A_RESID}'

    response = client.put(url, json={'name': ' Tacos ', 'city': ' NY '})
    assert response.status_code == 200
    assert response.get_json()['restaurant'] == {
        '_id': A_RESID, 'user': 'bob', 'name': 'Tacos', 'city': 'NY',
        'cuisine': '', 'notes': '', 'rating': None, 'location': None,
        'neighborhood': None}

    assert client.delete(url).status_code == 200


@pytest.mark.parametrize('payload', [
    {}, [], {'name': 'Tacos'}, {'name': ' ', 'city': 'NY'},
    {'name': 'Tacos', 'city': 'NY', 'notes': 42},
    {'name': 'Tacos', 'city': 'NY', 'rating': 11},
    {'name': 'Tacos', 'city': 'NY', 'rating': '9'},
    {'name': 'Tacos', 'city': 'NY', 'rating': True},
])
@patch('data.db_connect.create', autospec=True)
def test_invalid_restaurant(create, payload):
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    assert client.post(ep.RESTAURANTS_EP, json=payload).status_code == 400
    create.assert_not_called()


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[], autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_personal_list(create, read, connect):
    create.return_value.inserted_id = '123'
    for username in ('bob', 'alice'):
        client = ep.app.test_client()
        token = create_access_token(
            username, TEST_JWT_SECRET)
        client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        response = client.post(ep.RESTAURANTS_EP, json={
            'name': ' Tacos ', 'city': ' NY ', 'user': 'someone-else'})
        assert response.status_code == 201
        assert response.get_json()['restaurant'] == {
            '_id': '123', 'user': username, 'name': 'Tacos', 'city': 'NY',
            'cuisine': '', 'notes': '', 'rating': None,
            'neighborhood': None}
        response = client.get(ep.RESTAURANTS_EP + '?user=someone-else')
        assert response.get_json() == {'restaurants': []}
        read.assert_called_with(ep.RESTAURANTS_COLLECT, no_id=False,
                                filt={'user': username})


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', autospec=True)
def test_list_sorted_by_rating(read, connect):
    read.return_value = [{'name': 'a', 'rating': 5}, {'name': 'b'},
                         {'name': 'c', 'rating': 9.5},
                         {'name': 'd', 'rating': 0}]
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    names = [r['name'] for r in
             client.get(ep.RESTAURANTS_EP).get_json()['restaurants']]
    assert names == ['c', 'a', 'd', 'b']


SOHO = {
    '_id': 'nyc-soho', 'type': 'neighborhood', 'name': 'SoHo',
    'borough': 'Manhattan', 'code': 'MN0201',
    'boundary': {'type': 'MultiPolygon', 'coordinates': []},
}


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=dict(SOHO), autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_create_in_neighborhood(create, read_one, connect):
    create.return_value.inserted_id = '123'
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.post(ep.RESTAURANTS_EP, json={
        'name': 'Tacos', 'city': 'NY', 'lat': 40.72, 'lon': -74.0})
    assert response.status_code == 201
    restaurant = response.get_json()['restaurant']
    assert restaurant['location'] == {
        'type': 'Point', 'coordinates': [-74.0, 40.72]}
    assert restaurant['neighborhood'] == {
        'name': 'SoHo', 'borough': 'Manhattan', 'code': 'MN0201'}
    stored = create.call_args.args[1]
    assert stored['location'] == restaurant['location']
    assert stored['neighborhood'] == restaurant['neighborhood']


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=None, autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_create_outside_neighborhoods(create, read_one, connect):
    create.return_value.inserted_id = '123'
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.post(ep.RESTAURANTS_EP, json={
        'name': 'Tacos', 'city': 'NY', 'lat': 0, 'lon': 0})
    assert response.status_code == 201
    restaurant = response.get_json()['restaurant']
    assert restaurant['location'] == {
        'type': 'Point', 'coordinates': [0.0, 0.0]}
    assert restaurant['neighborhood'] is None
    assert create.call_args.args[1]['neighborhood'] is None


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_create_without_location(create, read_one, connect):
    create.return_value.inserted_id = '123'
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.post(
        ep.RESTAURANTS_EP, json={'name': 'Tacos', 'city': 'NY'})
    assert response.status_code == 201
    restaurant = response.get_json()['restaurant']
    assert 'location' not in restaurant
    assert restaurant['neighborhood'] is None
    read_one.assert_not_called()


@pytest.mark.parametrize('coords,message', [
    ({'lat': 40.72}, 'lat and lon must be given together'),
    ({'lon': -74.0}, 'lat and lon must be given together'),
    ({'lat': '40.72', 'lon': -74.0}, 'lat and lon must be numbers'),
    ({'lat': True, 'lon': -74.0}, 'lat and lon must be numbers'),
    ({'lat': 91, 'lon': -74.0}, ep.LAT_LON_RANGE_ERROR),
    ({'lat': 40.72, 'lon': -181}, ep.LAT_LON_RANGE_ERROR),
    ({'lat': 10 ** 400, 'lon': 0}, ep.LAT_LON_RANGE_ERROR),
])
@patch('data.db_connect.create', autospec=True)
def test_invalid_location(create, coords, message):
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.post(
        ep.RESTAURANTS_EP, json={'name': 'Tacos', 'city': 'NY', **coords})
    assert response.status_code == 400
    assert response.get_json()[ep.MESSAGE] == message
    create.assert_not_called()


@patch('data.db_connect.create', autospec=True)
def test_nan_location(create):
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    # json= can't encode NaN; Flask's parser accepts the raw literal.
    response = client.post(
        ep.RESTAURANTS_EP, content_type='application/json',
        data='{"name": "Tacos", "city": "NY", "lat": NaN, "lon": 0}')
    assert response.status_code == 400
    assert response.get_json()[ep.MESSAGE] == ep.LAT_LON_RANGE_ERROR
    create.assert_not_called()


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=dict(SOHO), autospec=True)
@patch('data.db_connect.update', autospec=True)
def test_update_with_location(update, read_one, connect):
    update.return_value = MagicMock(matched_count=1)
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.put(
        ep.RESTAURANTS_EP + f'/{A_RESID}',
        json={'name': 'Tacos', 'city': 'NY', 'lat': 40.72, 'lon': -74.0})
    assert response.status_code == 200
    stored = update.call_args.args[2]
    assert stored['location']['coordinates'] == [-74.0, 40.72]
    assert stored['neighborhood']['name'] == 'SoHo'


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', autospec=True)
@patch('data.db_connect.update', autospec=True)
def test_update_without_location_clears_it(update, read_one, connect):
    update.return_value = MagicMock(matched_count=1)
    client = ep.app.test_client()
    token = create_access_token(
        'bob', TEST_JWT_SECRET)
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    response = client.put(
        ep.RESTAURANTS_EP + f'/{A_RESID}',
        json={'name': 'Tacos', 'city': 'NY'})
    assert response.status_code == 200
    stored = update.call_args.args[2]
    assert stored['location'] is None
    assert stored['neighborhood'] is None
    restaurant = response.get_json()['restaurant']
    assert restaurant['location'] is None
    assert restaurant['neighborhood'] is None
    read_one.assert_not_called()


@pytest.mark.parametrize('method,path', [
    ('get', '/restaurants'),
    ('post', '/restaurants'),
    ('put', '/restaurants/' + A_RESID),
    ('delete', '/restaurants/' + A_RESID),
])
@pytest.mark.parametrize('kind', ['invalid', 'wrong-key', 'cookie'])
@patch('data.db_connect.connect_db', autospec=True)
def test_reject_bad_auth(connect, method, path, kind):
    client = ep.app.test_client()
    headers = {}
    if kind == 'invalid':
        headers['Authorization'] = 'Bearer invalid-token'
    elif kind == 'wrong-key':
        token = create_access_token('bob', 'wrong-signing-key' * 3)
        headers['Authorization'] = f'Bearer {token}'
    else:
        with client.session_transaction() as sess:
            sess['user'] = 'bob'
    response = getattr(client, method)(path, headers=headers)
    assert response.status_code == 401
    connect.assert_not_called()
