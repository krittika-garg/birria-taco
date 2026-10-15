import os
from uuid import uuid4

import pytest
import pymongo as pm

import data.db_connect as dbc
import places.load as load

STATE_ROWS = [
    {'Abbrev': 'NY', 'Latitude': '43.299428', 'Longitude': '-74.217933',
     'State': 'New York'},
    {'Abbrev': 'NJ', 'Latitude': '40.058324', 'Longitude': '-74.405661',
     'State': 'New Jersey'},
]
CITY_ROWS = [
    {'name': ' New York City ', 'state': 'ny', 'latitude': '40.712776',
     'longitude': '-74.005974'},
]


SQUARE = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
HOLE = [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]

NYC_ID = 'us-ny-new-york-city'


def _neighborhood(name, coordinates=None):
    return {
        'type': 'Feature',
        'properties': {'name': name, 'borough': 'Manhattan',
                       'code': 'MN0000', 'residential': True},
        'geometry': {'type': 'MultiPolygon',
                     'coordinates': coordinates or [[SQUARE]]},
    }


def _by_id(places):
    return {place['_id']: place for place in places}


def test_slugify():
    assert load.slugify('New York City') == 'new-york-city'
    assert load.slugify("  St. Mark's Place ") == 'st-mark-s-place'


def test_slugify_rejects_empty():
    with pytest.raises(ValueError):
        load.slugify('!!!')


def test_geo_point_is_lng_lat():
    assert load.geo_point('40.5', '-74.25') == {
        'type': 'Point', 'coordinates': [-74.25, 40.5]}


@pytest.mark.parametrize('lat, lng', [('91', '0'), ('0', '-181')])
def test_geo_point_rejects_out_of_range(lat, lng):
    with pytest.raises(ValueError):
        load.geo_point(lat, lng)


def test_build_places_hierarchy():
    places = _by_id(load.build_places(STATE_ROWS, CITY_ROWS))

    assert set(places) == {'us', 'us-ny', 'us-nj', 'us-ny-new-york-city'}
    assert places['us']['parent_id'] is None
    assert places['us-ny']['type'] == load.STATE
    assert places['us-ny']['abbrev'] == 'NY'
    assert places['us-ny']['parent_id'] == 'us'

    nyc = places['us-ny-new-york-city']
    assert nyc['type'] == load.CITY
    assert nyc['name'] == 'New York City'
    assert nyc['parent_id'] == 'us-ny'
    assert nyc['ancestors'] == ['us', 'us-ny']
    assert nyc['location']['coordinates'] == [-74.005974, 40.712776]


def test_build_places_unknown_state():
    rows = [dict(CITY_ROWS[0], state='ZZ')]
    with pytest.raises(ValueError, match='unknown state'):
        load.build_places(STATE_ROWS, rows)


def test_build_places_duplicate_city():
    with pytest.raises(ValueError, match='duplicate'):
        load.build_places(STATE_ROWS, CITY_ROWS * 2)


def test_centroid_of_square():
    assert load.multipolygon_centroid([[SQUARE]]) == (2, 2)


def test_centroid_subtracts_holes():
    # Square minus its top-right quarter: the L shape's centroid
    # shifts toward the bottom left.
    lat, lng = load.multipolygon_centroid([[SQUARE, HOLE]])
    assert lat == pytest.approx(5 / 3)
    assert lng == pytest.approx(5 / 3)


def test_centroid_weights_polygons_by_area():
    small = [[10, 0], [11, 0], [11, 1], [10, 1], [10, 0]]
    lat, lng = load.multipolygon_centroid([[SQUARE], [small]])
    assert lng == pytest.approx((16 * 2 + 1 * 10.5) / 17)
    assert lat == pytest.approx((16 * 2 + 1 * 0.5) / 17)


def test_centroid_rejects_flat_ring():
    with pytest.raises(ValueError):
        load.multipolygon_centroid([[[[0, 0], [1, 1], [0, 0]]]])


def test_build_places_neighborhoods():
    places = _by_id(load.build_places(
        STATE_ROWS, CITY_ROWS,
        {NYC_ID: [_neighborhood('East Village')]}))

    hood = places[f'{NYC_ID}-east-village']
    assert hood['type'] == load.NEIGHBORHOOD
    assert hood['parent_id'] == NYC_ID
    assert hood['ancestors'] == ['us', 'us-ny', NYC_ID]
    assert hood['borough'] == 'Manhattan'
    assert hood['residential'] is True
    assert hood['location']['coordinates'] == [2, 2]
    assert hood['boundary']['type'] == 'MultiPolygon'


def test_build_places_neighborhoods_unknown_city():
    with pytest.raises(ValueError, match='unknown city'):
        load.build_places(STATE_ROWS, CITY_ROWS,
                          {'us-nj-newark': [_neighborhood('Ironbound')]})


def test_build_neighborhoods_requires_multipolygon():
    feature = _neighborhood('Flat')
    feature['geometry']['type'] = 'Polygon'
    with pytest.raises(ValueError, match='MultiPolygon'):
        load.build_places(STATE_ROWS, CITY_ROWS, {NYC_ID: [feature]})


def _real_places():
    return load.build_places(load.read_csv(load.STATES_CSV),
                             load.read_csv(load.CITIES_CSV),
                             load.read_neighborhoods())


def test_raw_data_loads():
    places = _by_id(_real_places())
    assert NYC_ID in places
    assert places['us-ny']['name'] == 'New York'

    hoods = [p for p in places.values() if p['type'] == load.NEIGHBORHOOD]
    assert len(hoods) == 262
    assert {h['borough'] for h in hoods} == {
        'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'}
    for hood in hoods:
        lng, lat = hood['location']['coordinates']
        # Every centroid lands inside NYC's bounding box.
        assert 40.49 < lat < 40.92 and -74.26 < lng < -73.69, hood['_id']

    lng, lat = places[f'{NYC_ID}-greenpoint']['location']['coordinates']
    assert lat == pytest.approx(40.73, abs=0.01)
    assert lng == pytest.approx(-73.95, abs=0.01)


@pytest.fixture
def test_db(monkeypatch):
    if os.environ.get('CLOUD_MONGO', dbc.LOCAL) == dbc.CLOUD:
        uri = os.environ['MONGO_URI']
    else:
        uri = 'mongodb://localhost:27017/'
    client = pm.MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command('ping')
    except pm.errors.ServerSelectionTimeoutError:
        client.close()
        pytest.skip('MongoDB is not reachable')
    monkeypatch.setattr(dbc, 'client', client)
    database = f'places_test_{uuid4().hex}'
    try:
        yield client[database]
    finally:
        client.drop_database(database)
        client.close()


def test_save_places_is_idempotent(test_db):
    places = load.build_places(STATE_ROWS, CITY_ROWS)
    load.save_places(places, db=test_db.name)
    load.save_places(places, db=test_db.name)

    collection = test_db[load.PLACES_COLLECT]
    assert collection.count_documents({}) == len(places)
    in_ny = collection.find({'ancestors': 'us-ny'})
    assert [place['_id'] for place in in_ny] == ['us-ny-new-york-city']

    near_nyc = collection.find_one({'type': load.CITY, 'location': {
        '$near': {'$geometry': load.geo_point('40.73', '-73.99')}}})
    assert near_nyc['_id'] == 'us-ny-new-york-city'


def test_save_real_neighborhoods(test_db):
    # Inserting every real boundary checks that MongoDB's 2dsphere index
    # accepts all of them.
    load.save_places(_real_places(), db=test_db.name)

    collection = test_db[load.PLACES_COLLECT]
    times_square = load.geo_point('40.7580', '-73.9855')
    hood = collection.find_one({'type': load.NEIGHBORHOOD, 'boundary': {
        '$geoIntersects': {'$geometry': times_square}}})
    assert hood['name'] == 'Midtown-Times Square'
