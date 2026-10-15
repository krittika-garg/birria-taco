import places.fetch_nyc_neighborhoods as fetch


def test_trim_ring_rounds_and_drops_repeats():
    ring = [[-73.1234561, 40.1], [-73.1234564, 40.1], [-73.2, 40.2],
            [-73.1234561, 40.1]]
    assert fetch.trim_ring(ring) == [
        [-73.123456, 40.1], [-73.2, 40.2], [-73.123456, 40.1]]


def test_trim_feature():
    feature = {
        'properties': {'ntaname': 'Greenpoint', 'boroname': 'Brooklyn',
                       'nta2020': 'BK0101', 'ntatype': '0',
                       'shape_area': '1'},
        'geometry': {'type': 'MultiPolygon',
                     'coordinates': [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]},
    }
    trimmed = fetch.trim_feature(feature)
    assert trimmed['properties'] == {
        'name': 'Greenpoint', 'borough': 'Brooklyn', 'code': 'BK0101',
        'residential': True}
    assert trimmed['geometry'] == feature['geometry']

    feature['properties']['ntatype'] = '9'
    assert fetch.trim_feature(feature)['properties']['residential'] is False
