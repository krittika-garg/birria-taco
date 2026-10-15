#!/usr/bin/env python3
"""
Load the place hierarchy (country -> state -> city -> neighborhood) into
the places collection. Restaurants point at a city's _id through their
city_id.

States come from states/raw_data/states.csv; cities come from
places/raw_data/cities.csv; each city's neighborhoods come from
places/raw_data/neighborhoods/<city _id>.geojson.
"""

import csv
import glob
import json
import os
import re
import sys

import data.db_connect as dbc

PLACES_COLLECT = 'places'

COUNTRY = 'country'
STATE = 'state'
CITY = 'city'
NEIGHBORHOOD = 'neighborhood'

COUNTRY_ID = 'us'
COUNTRY_NAME = 'United States'

HERE = os.path.dirname(os.path.abspath(__file__))
STATES_CSV = os.path.join(HERE, '..', 'states', 'raw_data', 'states.csv')
CITIES_CSV = os.path.join(HERE, 'raw_data', 'cities.csv')
NEIGHBORHOODS_DIR = os.path.join(HERE, 'raw_data', 'neighborhoods')


def slugify(text):
    """
    Turn a name into a lowercase, hyphenated id fragment.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    if not slug:
        raise ValueError(f'cannot make an id from {text!r}')
    return slug


def geo_point(lat, lng):
    """
    Return a GeoJSON point. GeoJSON puts longitude first.
    """
    lat, lng = float(lat), float(lng)
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ValueError(f'bad coordinates: {lat}, {lng}')
    return {'type': 'Point', 'coordinates': [lng, lat]}


def _ring_centroid(ring):
    """
    Return (area, x, y) for a closed ring using the shoelace formula.
    The area is signed; the centroid doesn't depend on the sign.
    """
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area /= 2
    if area == 0:
        raise ValueError('ring has no area')
    return area, cx / (6 * area), cy / (6 * area)


def multipolygon_centroid(coordinates):
    """
    Return the (lat, lng) centroid of GeoJSON MultiPolygon coordinates,
    weighting each polygon by area and subtracting holes. Treating
    degrees as flat is fine at neighborhood scale. For an oddly shaped
    neighborhood the centroid can fall just outside it.
    """
    total = x_sum = y_sum = 0.0
    for polygon in coordinates:
        for i, ring in enumerate(polygon):
            area, x, y = _ring_centroid(ring)
            weight = abs(area) if i == 0 else -abs(area)
            total += weight
            x_sum += weight * x
            y_sum += weight * y
    return y_sum / total, x_sum / total


def read_csv(file_path):
    with open(file_path, mode='r', newline='') as csvfile:
        return list(csv.DictReader(csvfile))


def read_neighborhoods(directory=NEIGHBORHOODS_DIR):
    """
    Return {city _id: [GeoJSON features]} from <city _id>.geojson files.
    """
    neighborhoods = {}
    for file_path in sorted(glob.glob(os.path.join(directory, '*.geojson'))):
        city_id = os.path.basename(file_path)[:-len('.geojson')]
        with open(file_path) as geojson:
            neighborhoods[city_id] = json.load(geojson)['features']
    return neighborhoods


def build_neighborhoods(city, features):
    """
    Build neighborhood documents for a city from GeoJSON features with
    name, borough, code and residential properties and MultiPolygon
    geometry. The boundary is kept so restaurants can be matched to
    their neighborhood with $geoIntersects.
    """
    neighborhoods = []
    for feature in features:
        props = feature['properties']
        geometry = feature['geometry']
        if geometry['type'] != 'MultiPolygon':
            raise ValueError(f'{props["name"]!r} is not a MultiPolygon')
        lat, lng = multipolygon_centroid(geometry['coordinates'])
        neighborhoods.append({
            '_id': f'{city["_id"]}-{slugify(props["name"])}',
            'type': NEIGHBORHOOD,
            'name': props['name'],
            'borough': props['borough'],
            'code': props['code'],
            'residential': props['residential'],
            'parent_id': city['_id'],
            'ancestors': city['ancestors'] + [city['_id']],
            'location': geo_point(lat, lng),
            'boundary': geometry,
        })
    return neighborhoods


def build_places(state_rows, city_rows, neighborhoods=None):
    """
    Build place documents from state and city CSV rows, plus optional
    {city _id: [GeoJSON features]} neighborhoods.
    Every place gets a stable string _id, so reloading updates places
    in place instead of duplicating them, and ancestors lists every
    place above it, so "everything in New York State" is one query.
    """
    country = {
        '_id': COUNTRY_ID,
        'type': COUNTRY,
        'name': COUNTRY_NAME,
        'parent_id': None,
        'ancestors': [],
    }
    places = [country]

    states = {}
    for row in state_rows:
        abbrev = row['Abbrev'].strip().upper()
        state = {
            '_id': f'{COUNTRY_ID}-{abbrev.lower()}',
            'type': STATE,
            'name': row['State'].strip(),
            'abbrev': abbrev,
            'parent_id': COUNTRY_ID,
            'ancestors': [COUNTRY_ID],
            'location': geo_point(row['Latitude'], row['Longitude']),
        }
        states[abbrev] = state
        places.append(state)

    cities = {}
    for row in city_rows:
        abbrev = row['state'].strip().upper()
        state = states.get(abbrev)
        if state is None:
            raise ValueError(f'city {row["name"]!r} has unknown state '
                             f'{abbrev!r}')
        name = row['name'].strip()
        city = {
            '_id': f'{state["_id"]}-{slugify(name)}',
            'type': CITY,
            'name': name,
            'parent_id': state['_id'],
            'ancestors': state['ancestors'] + [state['_id']],
            'location': geo_point(row['latitude'], row['longitude']),
        }
        cities[city['_id']] = city
        places.append(city)

    for city_id, features in (neighborhoods or {}).items():
        if city_id not in cities:
            raise ValueError(f'neighborhoods for unknown city {city_id!r}')
        places.extend(build_neighborhoods(cities[city_id], features))

    ids = [place['_id'] for place in places]
    dupes = sorted({pid for pid in ids if ids.count(pid) > 1})
    if dupes:
        raise ValueError(f'duplicate place ids: {dupes}')
    return places


def save_places(places, db=dbc.SE_DB):
    """
    Upsert places by _id and make sure the indexes exist.
    """
    dbc.create_index(PLACES_COLLECT, [('location', '2dsphere')], db=db)
    dbc.create_index(PLACES_COLLECT, [('boundary', '2dsphere')], db=db)
    dbc.create_index(PLACES_COLLECT, [('type', 1), ('parent_id', 1)], db=db)
    dbc.create_index(PLACES_COLLECT, [('ancestors', 1)], db=db)
    for place in places:
        fields = {k: v for k, v in place.items() if k != dbc.MONGO_ID}
        dbc.upsert(PLACES_COLLECT, {dbc.MONGO_ID: place[dbc.MONGO_ID]},
                   fields, db=db)


def main():
    states_csv = sys.argv[1] if len(sys.argv) > 1 else STATES_CSV
    cities_csv = sys.argv[2] if len(sys.argv) > 2 else CITIES_CSV
    places = build_places(read_csv(states_csv), read_csv(cities_csv),
                          read_neighborhoods())
    dbc.connect_db()
    save_places(places)
    print(f'Imported {len(places)} place records.')


if __name__ == '__main__':
    main()
