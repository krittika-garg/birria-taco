"""State lookups against the real states CSV loaded into MongoDB."""
import os

import pytest

import data.db_connect as dbc
from server.states import haversine_km
from states.load import load_states

STATES_CSV = os.path.join(os.path.dirname(__file__), '..', '..', 'states',
                          'raw_data', 'states.csv')


@pytest.fixture
def states(db):
    rows = load_states(STATES_CSV)
    for row in rows:
        dbc.upsert('states', {'Abbrev': row['Abbrev']}, dict(row))
    return rows


def test_all_states(anon, states):
    listed = anon.get('/states').get_json()['states']
    assert len(listed) == len(states)
    assert all('_id' not in state for state in listed)


def test_one_state_case_insensitive(anon, states):
    response = anon.get('/states/ny')
    assert response.status_code == 200
    assert response.get_json()['state']['Abbrev'] == 'NY'
    assert anon.get('/states/zz').status_code == 404


def test_loading_twice_does_not_duplicate(anon, states):
    for row in states:
        dbc.upsert('states', {'Abbrev': row['Abbrev']}, dict(row))
    assert len(anon.get('/states').get_json()['states']) == len(states)


def test_nearest_state(anon, states):
    lat, lon = 40.7128, -74.0060
    expected = min(states, key=lambda s: haversine_km(
        lat, lon, s['Latitude'], s['Longitude']))
    body = anon.get(f'/states/nearest?lat={lat}&lon={lon}').get_json()
    assert body['state']['Abbrev'] == expected['Abbrev']
    assert body['distance_km'] == round(haversine_km(
        lat, lon, expected['Latitude'], expected['Longitude']), 2)
