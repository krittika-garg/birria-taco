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
