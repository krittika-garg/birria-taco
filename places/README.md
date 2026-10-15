# Places

The place hierarchy (country -> state -> city -> neighborhood) that
restaurants hang off. Each restaurant will store the `_id` of its city as
`city_id`.

Load it with:

~~~
PYTHONPATH=$(pwd) python places/load.py
~~~

States come from `states/raw_data/states.csv` and cities from
`places/raw_data/cities.csv`. Reloading is safe: places are upserted by
their `_id`.

Each document in the `places` collection looks like:

~~~
{
  "_id": "us-ny-new-york-city",
  "type": "city",
  "name": "New York City",
  "parent_id": "us-ny",
  "ancestors": ["us", "us-ny"],
  "location": {"type": "Point", "coordinates": [-74.005974, 40.712776]}
}
~~~

Ids are built from names (`us`, `us-ny`, `us-ny-new-york-city`), so they
stay the same across reloads and environments. `ancestors` lets one query
find everything inside a state or country. `location` is a GeoJSON point
(longitude first) with a 2dsphere index.

To add a city, add a row to `raw_data/cities.csv` and rerun the loader.

## Neighborhoods

A city's neighborhoods live in `raw_data/neighborhoods/<city _id>.geojson`:
GeoJSON features with `name`, `borough`, `code` and `residential`
properties and MultiPolygon geometry. Neighborhood documents add those
fields plus `boundary` (the MultiPolygon, with a 2dsphere index), and
their `location` is the boundary's centroid. Their ids extend the city's,
e.g. `us-ny-new-york-city-east-village`.

To find which neighborhood a point is in:

~~~
db.places.findOne({type: "neighborhood", boundary: {$geoIntersects:
  {$geometry: {type: "Point", coordinates: [-73.9855, 40.7580]}}}})
~~~

NYC uses the 262 2020 Neighborhood Tabulation Areas from the NYC
Department of City Planning (via NYC Open Data). 197 are residential; the
rest are parks, cemeteries, airports and other special areas, flagged with
`residential: false` so leaderboards can hide them. To refresh the file:

~~~
python places/fetch_nyc_neighborhoods.py
~~~
