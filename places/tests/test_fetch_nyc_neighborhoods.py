import places.fetch_nyc_neighborhoods as fetch


A = [-73.123456, 40.1]
B = [-73.2, 40.2]
C = [-73.3, 40.1]
D = [-73.2, 40.0]


def test_trim_ring_rounds_and_drops_repeats():
    # A' rounds to A, so it's a repeat.
    ring = [[-73.1234561, 40.1], [-73.1234564, 40.1], B, C,
            [-73.1234561, 40.1]]
    assert fetch.trim_ring(ring) == [A, B, C, A]


def test_trim_ring_drops_spike():
    # The College Point case: a ~10 cm out-and-back from B.
    ring = [A, B, [-73.2, 40.200001], B, C, A]
    assert fetch.trim_ring(ring) == [A, B, C, A]


def test_trim_ring_drops_nested_spike():
    # Dropping C leaves B, D, B, which is a spike too.
    ring = [A, B, D, C, D, B, C, A]
    assert fetch.trim_ring(ring) == [A, B, C, A]


def test_trim_ring_drops_spike_across_closing_point():
    # [A, B, C, D, B, A] goes out to B and back at the start and end.
    ring = [A, B, C, D, B, A]
    assert fetch.trim_ring(ring) == [B, C, D, B]


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
