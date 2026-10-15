#!/usr/bin/env python3
"""
Download NYC's 2020 Neighborhood Tabulation Areas (NYC Department of
City Planning, via NYC Open Data) and save a trimmed copy for load.py.

Only rerun this to refresh the data; the output is committed.
"""

import json
import os
import urllib.request

SOURCE_URL = ('https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson'
              '?$limit=1000')
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'raw_data', 'neighborhoods',
                        'us-ny-new-york-city.geojson')

# NTA types other than 0 are parks, cemeteries, airports and the like.
RESIDENTIAL_TYPE = '0'
# 6 decimal places is about 10 cm, plenty for neighborhood lines.
PRECISION = 6


def trim_ring(ring):
    """
    Round a ring's points and remove what rounding breaks: repeated
    points (A, A) and out-and-back spikes (A, B, A), including a spike
    across the closing point. MongoDB's 2dsphere index rejects any
    repeated vertex other than the closing one.
    """
    trimmed = []
    for lng, lat in ring:
        point = [round(lng, PRECISION), round(lat, PRECISION)]
        if trimmed and point == trimmed[-1]:
            continue
        if len(trimmed) >= 2 and point == trimmed[-2]:
            # A, B, A: drop B; the ring is back at A already.
            trimmed.pop()
            continue
        trimmed.append(point)
    # [A, B, ..., B, A]: the spike wraps around the closing point.
    while len(trimmed) >= 4 and trimmed[1] == trimmed[-2]:
        trimmed = trimmed[1:-1]
    return trimmed


def trim_feature(feature):
    props = feature['properties']
    geometry = feature['geometry']
    return {
        'type': 'Feature',
        'properties': {
            'name': props['ntaname'],
            'borough': props['boroname'],
            'code': props['nta2020'],
            'residential': props['ntatype'] == RESIDENTIAL_TYPE,
        },
        'geometry': {
            'type': geometry['type'],
            'coordinates': [[trim_ring(ring) for ring in polygon]
                            for polygon in geometry['coordinates']],
        },
    }


def main():
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        source = json.load(response)
    features = sorted((trim_feature(f) for f in source['features']),
                      key=lambda f: f['properties']['code'])
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w') as out:
        json.dump({'type': 'FeatureCollection', 'features': features}, out,
                  separators=(',', ':'))
        out.write('\n')
    print(f'Saved {len(features)} neighborhoods to {OUT_FILE}')


if __name__ == '__main__':
    main()
