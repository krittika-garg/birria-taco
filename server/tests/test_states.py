from http.client import BAD_REQUEST, NOT_FOUND, OK

from unittest.mock import patch

import pytest

from server.endpoints import app
import server.states as st


TEST_CLIENT = app.test_client()


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[{'Abbrev': 'NY'}], autospec=True)
def test_states(mock_read, mock_connect):
    resp = TEST_CLIENT.get(st.STATES_EP)
    assert resp.status_code == OK
    assert resp.get_json() == {st.STATES_RESP: [{'Abbrev': 'NY'}]}
    mock_read.assert_called_once_with(st.STATES_COLLECT)


NY = {'Abbrev': 'NY', 'Name': 'New York',
      'Latitude': 42.9538, 'Longitude': -75.5268}
CA = {'Abbrev': 'CA', 'Name': 'California',
      'Latitude': 36.7783, 'Longitude': -119.4179}


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one',
       return_value={'_id': 'abc', **NY}, autospec=True)
def test_state_by_abbrev(mock_read_one, mock_connect):
    resp = TEST_CLIENT.get(f'{st.STATES_EP}/ny')
    assert resp.status_code == OK
    assert resp.get_json() == {'state': NY}
    mock_read_one.assert_called_once_with(st.STATES_COLLECT, {'Abbrev': 'NY'})


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read_one', return_value=None, autospec=True)
def test_state_by_abbrev_not_found(mock_read_one, mock_connect):
    resp = TEST_CLIENT.get(f'{st.STATES_EP}/ZZ')
    assert resp.status_code == NOT_FOUND


def test_haversine_same_point_is_zero():
    assert st.haversine_km(40.0, -74.0, 40.0, -74.0) == 0


def test_haversine_known_distance():
    # NYC to LA is roughly 3,940 km
    dist = st.haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < dist < 3980


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[NY, CA], autospec=True)
def test_nearest_state(mock_read, mock_connect):
    # Coordinates in Manhattan should resolve to New York
    resp = TEST_CLIENT.get(
        f'{st.STATES_EP}/nearest', query_string={'lat': 40.71, 'lon': -74.0})
    assert resp.status_code == OK
    body = resp.get_json()
    assert body['state']['Abbrev'] == 'NY'
    assert body['distance_km'] > 0


@pytest.mark.parametrize('params', [
    {},
    {'lat': 'abc', 'lon': '-74'},
    {'lat': '91', 'lon': '0'},
    {'lat': '0', 'lon': '181'},
    {'lat': 'nan', 'lon': '0'},
])
def test_nearest_state_bad_params(params):
    resp = TEST_CLIENT.get(f'{st.STATES_EP}/nearest', query_string=params)
    assert resp.status_code == BAD_REQUEST


@patch('data.db_connect.connect_db', autospec=True)
@patch('data.db_connect.read', return_value=[], autospec=True)
def test_nearest_state_no_data(mock_read, mock_connect):
    resp = TEST_CLIENT.get(
        f'{st.STATES_EP}/nearest', query_string={'lat': 0, 'lon': 0})
    assert resp.status_code == NOT_FOUND
