from unittest.mock import MagicMock, patch

import pytest

import server.endpoints as ep

A_RESID = '507f1f77bcf86cd799439011'


@pytest.mark.parametrize('method', ['get', 'post'])
def test_login_required(method):
    response = getattr(ep.app.test_client(), method)(ep.RESTAURANTS_EP)
    assert response.status_code == 401


@pytest.mark.parametrize('method', ['get', 'put', 'delete'])
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
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
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
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    url = ep.RESTAURANTS_EP + f'/{A_RESID}'

    response = client.put(url, json={'name': ' Tacos ', 'city': ' NY '})
    assert response.status_code == 200
    assert response.get_json()['restaurant'] == {
        '_id': A_RESID, 'user': 'bob', 'name': 'Tacos', 'city': 'NY',
        'cuisine': '', 'notes': '', 'rating': None}

    assert client.delete(url).status_code == 200


@pytest.mark.parametrize('payload', [
    {}, [], {'name': 'Tacos'}, {'name': ' ', 'city': 'NY'},
    {'name': 'Tacos', 'city': 'NY', 'notes': 42},
    {'name': 'Tacos', 'city': 'NY', 'rating': 11},
    {'name': 'Tacos', 'city': 'NY', 'rating': -1},
    {'name': 'Tacos', 'city': 'NY', 'rating': '9'},
    {'name': 'Tacos', 'city': 'NY', 'rating': True},
])
@patch('data.db_connect.create', autospec=True)
def test_invalid_restaurant(create, payload):
    client = ep.app.test_client()
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    assert client.post(ep.RESTAURANTS_EP, json=payload).status_code == 400
    create.assert_not_called()


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[], autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_personal_list(create, read, connect):
    create.return_value.inserted_id = '123'
    for username in ('bob', 'alice'):
        client = ep.app.test_client()
        with client.session_transaction() as sess:
            sess['user'] = username
        response = client.post(ep.RESTAURANTS_EP, json={
            'name': ' Tacos ', 'city': ' NY ', 'user': 'someone-else'})
        assert response.status_code == 201
        assert response.get_json()['restaurant'] == {
            '_id': '123', 'user': username, 'name': 'Tacos', 'city': 'NY',
            'cuisine': '', 'notes': '', 'rating': None}
        response = client.get(ep.RESTAURANTS_EP + '?user=someone-else')
        assert response.get_json() == {'restaurants': []}
        read.assert_called_with(ep.RESTAURANTS_COLLECT, no_id=False,
                                filt={'user': username})


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.create', autospec=True)
def test_rating_saved(create, connect):
    create.return_value.inserted_id = '123'
    client = ep.app.test_client()
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    response = client.post(ep.RESTAURANTS_EP, json={
        'name': 'Tacos', 'city': 'NY', 'rating': 8.5})
    assert response.status_code == 201
    assert response.get_json()['restaurant']['rating'] == 8.5


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', autospec=True)
def test_list_sorted_by_rating(read, connect):
    read.return_value = [
        {'name': 'a', 'rating': 3}, {'name': 'b'},
        {'name': 'c', 'rating': 9}, {'name': 'd', 'rating': None},
        {'name': 'e', 'rating': 0},
    ]
    client = ep.app.test_client()
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    names = [r['name'] for r in
             client.get(ep.RESTAURANTS_EP).get_json()['restaurants']]
    assert names[:3] == ['c', 'a', 'e']
    assert set(names[3:]) == {'b', 'd'}


@pytest.mark.parametrize('resid', [A_RESID, 'not-an-object-id'])
@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=None, autospec=True)
def test_get_one_not_found(read_one, connect, resid):
    client = ep.app.test_client()
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    response = client.get(ep.RESTAURANTS_EP + f'/{resid}')
    assert response.status_code == 404


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', autospec=True)
def test_get_one(read_one, connect):
    doc = {'_id': A_RESID, 'user': 'bob', 'name': 'Tacos', 'city': 'NY'}
    read_one.return_value = doc
    client = ep.app.test_client()
    with client.session_transaction() as sess:
        sess['user'] = 'bob'
    response = client.get(ep.RESTAURANTS_EP + f'/{A_RESID}')
    assert response.status_code == 200
    assert response.get_json() == {'restaurant': doc}
    # Ownership comes from the session, so other users' entries never match.
    filt = read_one.call_args[0][1]
    assert filt['user'] == 'bob' and str(filt['_id']) == A_RESID
