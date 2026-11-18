from http.client import BAD_REQUEST, NOT_FOUND, OK

from unittest.mock import patch

import pytest

import server.endpoints as ep
import server.neighborhoods as nb


TEST_CLIENT = ep.app.test_client()


SOHO = {
    '_id': 'nyc-soho', 'type': 'neighborhood', 'name': 'SoHo',
    'borough': 'Manhattan', 'code': 'MN0201',
    'parent_id': 'nyc', 'ancestors': ['us', 'ny'],
    'location': {'type': 'Point', 'coordinates': [-74.0, 40.72]},
    'boundary': {'type': 'MultiPolygon', 'coordinates': [[[
        [-74.01, 40.71], [-73.99, 40.71], [-73.99, 40.73], [-74.01, 40.71],
    ]]]},
}


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=dict(SOHO), autospec=True)
def test_neighborhood_at(mock_read_one, mock_connect):
    resp = TEST_CLIENT.get(
        nb.NEIGHBORHOOD_AT_EP, query_string={'lat': 40.72, 'lon': -74.0})
    assert resp.status_code == OK
    neighborhood = resp.get_json()['neighborhood']
    assert neighborhood['name'] == 'SoHo'
    assert 'boundary' not in neighborhood
    assert '_id' not in neighborhood
    mock_read_one.assert_called_once_with(nb.PLACES_COLLECT, {
        'type': nb.NEIGHBORHOOD,
        'boundary': {'$geoIntersects': {'$geometry': {
            'type': 'Point', 'coordinates': [-74.0, 40.72]}}},
    })


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=None, autospec=True)
def test_neighborhood_at_not_found(mock_read_one, mock_connect):
    resp = TEST_CLIENT.get(
        nb.NEIGHBORHOOD_AT_EP, query_string={'lat': 0, 'lon': 0})
    assert resp.status_code == NOT_FOUND


@pytest.mark.parametrize('params', [
    {},
    {'lat': 'abc', 'lon': '-74'},
    {'lat': '91', 'lon': '0'},
    {'lat': '0', 'lon': '181'},
    {'lat': 'nan', 'lon': '0'},
])
def test_neighborhood_at_bad_params(params):
    resp = TEST_CLIENT.get(nb.NEIGHBORHOOD_AT_EP, query_string=params)
    assert resp.status_code == BAD_REQUEST


def test_neighborhood_at_in_endpoints():
    resp = TEST_CLIENT.get(ep.ENDPOINT_EP)
    assert nb.NEIGHBORHOOD_AT_EP in resp.get_json()[ep.ENDPOINT_RESP]


@patch('data.db_connect.read', autospec=True, return_value=[
    {'name': 'Williamsburg'}, {'name': 'Astoria'}, {'name': 'SoHo'}])
def test_neighborhoods_sorted_by_name(mock_read):
    resp = TEST_CLIENT.get(nb.NEIGHBORHOODS_EP)
    assert resp.status_code == OK
    names = [hood['name'] for hood in resp.get_json()['neighborhoods']]
    assert names == ['Astoria', 'SoHo', 'Williamsburg']
    mock_read.assert_called_once_with(
        nb.PLACES_COLLECT, filt={'type': nb.NEIGHBORHOOD},
        projection={'boundary': 0})


@patch('data.db_connect.read', autospec=True, return_value=[])
def test_neighborhoods_empty_is_ok(mock_read):
    resp = TEST_CLIENT.get(nb.NEIGHBORHOODS_EP)
    assert resp.status_code == OK
    assert resp.get_json() == {'neighborhoods': []}


@pytest.mark.parametrize('given, canonical', [
    ('Brooklyn', 'Brooklyn'),
    ('brooklyn', 'Brooklyn'),
    ('  staten   ISLAND ', 'Staten Island'),
])
@patch('data.db_connect.read', autospec=True, return_value=[])
def test_neighborhoods_borough_filter(mock_read, given, canonical):
    resp = TEST_CLIENT.get(
        nb.NEIGHBORHOODS_EP, query_string={'borough': given})
    assert resp.status_code == OK
    mock_read.assert_called_once_with(
        nb.PLACES_COLLECT,
        filt={'type': nb.NEIGHBORHOOD, 'borough': canonical},
        projection={'boundary': 0})


@pytest.mark.parametrize('bad', ['', 'Hoboken', 'Manhatan'])
@patch('data.db_connect.read', autospec=True)
def test_neighborhoods_bad_borough(mock_read, bad):
    resp = TEST_CLIENT.get(
        nb.NEIGHBORHOODS_EP, query_string={'borough': bad})
    assert resp.status_code == BAD_REQUEST
    assert resp.get_json() == {nb.MESSAGE: nb.BOROUGH_ERROR}
    mock_read.assert_not_called()


def test_neighborhoods_in_endpoints():
    resp = TEST_CLIENT.get(ep.ENDPOINT_EP)
    assert nb.NEIGHBORHOODS_EP in resp.get_json()[ep.ENDPOINT_RESP]


def rated(name, *ratings):
    """Return one {'name', 'rating'} entry per rating."""
    return [{'name': name, 'rating': rating} for rating in ratings]


def test_leaderboard_empty():
    assert nb.leaderboard([]) == []


def test_leaderboard_single_ten_ranks_below_several_nines():
    entries = (rated('One Hit', 10) + rated('Steady', 9, 9, 9, 9, 9)
               + rated('Meh', 5, 5, 5, 5))
    names = [row['name'] for row in nb.leaderboard(entries)]
    assert names == ['Steady', 'One Hit', 'Meh']


def test_leaderboard_hand_worked_example():
    # m = (8 + 6 + 10) / 3 = 8
    # A: (3 * 8 + 14) / (3 + 2) = 7.6;  B: (3 * 8 + 10) / (3 + 1) = 8.5
    entries = rated('A', 8, 6) + rated('B', 10)
    assert nb.leaderboard(entries) == [
        {'name': 'B', 'score': 8.5, 'average': 10.0, 'ratings': 1},
        {'name': 'A', 'score': 7.6, 'average': 7.0, 'ratings': 2},
    ]


def test_leaderboard_rounds_to_two_decimals():
    # m = 22 / 3; score = (3 * 22/3 + 22) / 6 = 7.333...
    row, = nb.leaderboard(rated('A', 7, 7, 8))
    assert row == {'name': 'A', 'score': 7.33, 'average': 7.33,
                   'ratings': 3}


def test_leaderboard_prior_is_configurable():
    # prior=0 makes the score the plain average.
    entries = rated('A', 8, 6) + rated('B', 10)
    scores = {row['name']: row['score']
              for row in nb.leaderboard(entries, prior=0)}
    assert scores == {'A': 7.0, 'B': 10.0}


def test_leaderboard_groups_names_ignoring_case_and_whitespace():
    entries = (rated('Los Tacos No. 1', 9, 8)
               + rated('los tacos  no. 1', 7)
               + rated('  LOS TACOS NO. 1 ', 10))
    row, = nb.leaderboard(entries)
    assert row['name'] == 'Los Tacos No. 1'
    assert row['ratings'] == 4
    assert row['average'] == 8.5


@pytest.mark.parametrize('spellings, expected', [
    (['TAQUERIA', 'Taqueria'], 'Taqueria'),
    (['Taqueria', 'TAQUERIA'], 'Taqueria'),
    (['TAQUERIA', 'taqueria', 'Taqueria'], 'taqueria'),
])
def test_leaderboard_spelling_ties_break_case_insensitively(
        spellings, expected):
    entries = [{'name': name, 'rating': 8} for name in spellings]
    row, = nb.leaderboard(entries)
    assert row['name'] == expected


def test_leaderboard_most_common_spelling_beats_name_order():
    row, = nb.leaderboard(rated('TAQUERIA', 8, 9) + rated('Taqueria', 7))
    assert row['name'] == 'TAQUERIA'


def test_leaderboard_ties_sort_by_ratings_then_name():
    # Every rating equals the mean, so every score is 8.
    entries = rated('Beta', 8) + rated('Alpha', 8) + rated('Zeta', 8, 8)
    board = nb.leaderboard(entries)
    assert [row['score'] for row in board] == [8.0, 8.0, 8.0]
    assert [row['name'] for row in board] == ['Zeta', 'Alpha', 'Beta']


def test_leaderboard_name_ties_sort_case_insensitively():
    # Same score (all ratings equal the mean) and same rating count.
    entries = (rated("Zabar's", 8) + rated("applebee's", 8)
               + rated('Mamoun', 8) + rated('mamoun!', 8))
    names = [row['name'] for row in nb.leaderboard(entries)]
    assert names == ["applebee's", 'Mamoun', 'mamoun!', "Zabar's"]


def test_name_order_prefers_lowercase_among_case_variants():
    names = ['TAQUERIA', 'Zabar', 'Taqueria', 'apple', 'taqueria']
    assert sorted(names, key=nb.name_order) == [
        'apple', 'taqueria', 'Taqueria', 'TAQUERIA', 'Zabar']


def leaderboard_url(code):
    return f'/neighborhoods/{code}/leaderboard'


# What dbc.read might return: documents carrying _id and owner fields
# that must never reach the response.
SOHO_RESTAURANTS = [
    {'_id': 'r1', 'user': 'alice', 'name': 'Taqueria', 'rating': 9},
    {'_id': 'r2', 'user': 'bob', 'name': 'TAQUERIA', 'rating': 8},
    {'_id': 'r3', 'user': 'alice', 'name': 'Birria Spot', 'rating': 6},
]


@patch('data.db_connect.read', autospec=True,
       return_value=[dict(doc) for doc in SOHO_RESTAURANTS])
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('MN0201'))
    assert resp.status_code == OK
    body = resp.get_json()
    assert body['neighborhood'] == {
        'name': 'SoHo', 'borough': 'Manhattan', 'code': 'MN0201'}
    # m = 23 / 3; Taqueria: (23 + 17) / 5 = 8.0; Birria Spot: 29 / 4
    assert body['restaurants'] == [
        {'name': 'Taqueria', 'score': 8.0, 'average': 8.5, 'ratings': 2},
        {'name': 'Birria Spot', 'score': 7.25, 'average': 6.0,
         'ratings': 1},
    ]
    mock_read_one.assert_called_once_with(
        nb.PLACES_COLLECT, {'type': nb.NEIGHBORHOOD, 'code': 'MN0201'})
    mock_read.assert_called_once_with(
        'restaurants',
        filt={'neighborhood.code': 'MN0201', 'rating': {'$ne': None}},
        projection={'name': 1, 'rating': 1})


@patch('data.db_connect.read', autospec=True,
       return_value=[dict(doc) for doc in SOHO_RESTAURANTS])
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint_hides_users_and_ids(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('MN0201'))
    assert resp.status_code == OK
    text = resp.get_data(as_text=True)
    for leaked in ('_id', 'user', 'alice', 'bob', 'r1', 'nyc-soho',
                   'boundary'):
        assert leaked not in text


@patch('data.db_connect.read', autospec=True, return_value=[])
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint_lowercase_code(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('mn0201'))
    assert resp.status_code == OK
    mock_read_one.assert_called_once_with(
        nb.PLACES_COLLECT, {'type': nb.NEIGHBORHOOD, 'code': 'MN0201'})
    filt = mock_read.call_args.kwargs['filt']
    assert filt['neighborhood.code'] == 'MN0201'


@patch('data.db_connect.read', autospec=True, return_value=[])
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint_no_ratings(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('MN0201'))
    assert resp.status_code == OK
    assert resp.get_json()['restaurants'] == []


@patch('data.db_connect.read', autospec=True)
@patch('data.db_connect.read_one', autospec=True, return_value=None)
def test_leaderboard_endpoint_unknown_code(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('XX9999'))
    assert resp.status_code == NOT_FOUND
    assert resp.get_json() == {nb.MESSAGE: nb.NEIGHBORHOOD_NOT_FOUND}
    mock_read.assert_not_called()


@pytest.mark.parametrize('bad', ['0', '51', 'abc', '-1', '', '2.5'])
@patch('data.db_connect.read', autospec=True)
@patch('data.db_connect.read_one', autospec=True)
def test_leaderboard_endpoint_bad_limit(mock_read_one, mock_read, bad):
    resp = TEST_CLIENT.get(
        leaderboard_url('MN0201'), query_string={'limit': bad})
    assert resp.status_code == BAD_REQUEST
    assert resp.get_json() == {nb.MESSAGE: nb.LIMIT_ERROR}
    mock_read_one.assert_not_called()
    mock_read.assert_not_called()


MANY_RESTAURANTS = [
    {'name': f'Spot {i:02}', 'rating': i % 11} for i in range(12)]


@patch('data.db_connect.read', autospec=True, return_value=MANY_RESTAURANTS)
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint_default_limit(mock_read_one, mock_read):
    resp = TEST_CLIENT.get(leaderboard_url('MN0201'))
    restaurants = resp.get_json()['restaurants']
    assert len(restaurants) == nb.DEFAULT_LEADERBOARD_LIMIT == 10
    assert restaurants == nb.leaderboard(MANY_RESTAURANTS)[:10]


@pytest.mark.parametrize('limit', [1, 3, 50])
@patch('data.db_connect.read', autospec=True, return_value=MANY_RESTAURANTS)
@patch('data.db_connect.read_one', autospec=True, return_value=dict(SOHO))
def test_leaderboard_endpoint_limit(mock_read_one, mock_read, limit):
    resp = TEST_CLIENT.get(
        leaderboard_url('MN0201'), query_string={'limit': limit})
    assert resp.status_code == OK
    assert len(resp.get_json()['restaurants']) == min(limit, 12)
