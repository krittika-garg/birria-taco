"""Personal restaurant lists, geo queries and leaderboards on real Mongo."""
import pytest
from bson import ObjectId

TIMES_SQUARE = (40.7580, -73.9855)


def save(client, name, **fields):
    response = client.post('/restaurants', json={
        'name': name, 'city': 'New York', **fields})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['restaurant']


def test_crud_lifecycle(login):
    bob = login('bob')
    saved = save(bob, ' Los Tacos ', cuisine='Mexican', rating=9)
    assert saved['name'] == 'Los Tacos'
    url = f"/restaurants/{saved['_id']}"

    assert bob.get(url).get_json()['restaurant']['name'] == 'Los Tacos'

    response = bob.put(url, json={'name': 'Los Tacos No. 1',
                                  'city': 'New York', 'rating': 8})
    assert response.status_code == 200
    assert bob.get(url).get_json()['restaurant']['rating'] == 8

    assert bob.delete(url).status_code == 200
    assert bob.get(url).status_code == 404
    assert bob.delete(url).status_code == 404


def test_users_cannot_see_or_change_each_others_entries(login, db):
    bob, alice = login('bob'), login('alice')
    saved = save(bob, 'Los Tacos', rating=9)
    url = f"/restaurants/{saved['_id']}"

    assert alice.get('/restaurants').get_json() == {'restaurants': []}
    assert alice.get(url).status_code == 404
    assert alice.put(url, json={'name': 'Mine', 'city': 'NY'}).status_code \
        == 404
    assert alice.delete(url).status_code == 404
    assert db['restaurants'].find_one(
        {'_id': ObjectId(saved['_id'])})['name'] == 'Los Tacos'


def test_user_field_in_body_cannot_change_owner(login, db):
    bob = login('bob')
    saved = save(bob, 'Los Tacos', user='alice')
    stored = db['restaurants'].find_one({'_id': ObjectId(saved['_id'])})
    assert stored['user'] == 'bob'


def test_list_sorted_best_first_unrated_last(login):
    bob = login('bob')
    for name, rating in [('Ok', 5), ('Unrated', None), ('Great', 9)]:
        save(bob, name, rating=rating)
    names = [r['name'] for r in bob.get('/restaurants').get_json()[
        'restaurants']]
    assert names == ['Great', 'Ok', 'Unrated']


def test_filters_by_status_and_min_rating(login):
    bob = login('bob')
    save(bob, 'Great', rating=9)
    save(bob, 'Ok', rating=5)
    save(bob, 'Someday', status='want_to_try')

    def names(query):
        return sorted(r['name'] for r in bob.get(
            '/restaurants?' + query).get_json()['restaurants'])

    assert names('status=want_to_try') == ['Someday']
    assert names('min_rating=6') == ['Great']


def test_nearby_uses_real_geo_query(login):
    bob = login('bob')
    save(bob, 'Here', lat=40.7580, lon=-73.9855)
    save(bob, 'Close', lat=40.7614, lon=-73.9776)    # ~0.8 km
    save(bob, 'Brooklyn', lat=40.6782, lon=-73.9442)  # ~9.6 km
    save(bob, 'No location')

    response = bob.get('/restaurants/nearby?lat=40.7580&lon=-73.9855')
    found = response.get_json()['restaurants']
    assert [r['name'] for r in found] == ['Here', 'Close']
    assert found[1]['distance_km'] == pytest.approx(0.76, abs=0.05)

    wide = bob.get('/restaurants/nearby?lat=40.7580&lon=-73.9855'
                   '&radius_km=15').get_json()['restaurants']
    assert [r['name'] for r in wide] == ['Here', 'Close', 'Brooklyn']


def test_nearby_only_returns_your_own(login):
    bob, alice = login('bob'), login('alice')
    save(alice, 'Alices spot', lat=40.7580, lon=-73.9855)
    response = bob.get('/restaurants/nearby?lat=40.7580&lon=-73.9855')
    assert response.get_json()['restaurants'] == []


def test_location_is_tagged_with_real_neighborhood(login, neighborhoods):
    bob = login('bob')
    saved = save(bob, 'Los Tacos', lat=TIMES_SQUARE[0], lon=TIMES_SQUARE[1])
    assert saved['neighborhood']['name'] == 'Midtown-Times Square'
    assert saved['neighborhood']['borough'] == 'Manhattan'

    outside = save(bob, 'Philly cheesesteak', lat=39.9526, lon=-75.1652)
    assert outside['neighborhood'] is None


def test_neighborhood_at_point(anon, neighborhoods):
    response = anon.get('/neighborhoods/at?lat=40.7580&lon=-73.9855')
    assert response.get_json()['neighborhood']['name'] == \
        'Midtown-Times Square'
    response = anon.get('/neighborhoods/at?lat=0&lon=0')
    assert response.status_code == 404


def test_neighborhood_list_by_borough(anon, neighborhoods):
    hoods = anon.get('/neighborhoods?borough=staten%20island').get_json()[
        'neighborhoods']
    assert hoods
    assert {h['borough'] for h in hoods} == {'Staten Island'}
    assert all('boundary' not in h for h in hoods)
    assert [h['name'] for h in hoods] == sorted(h['name'] for h in hoods)


def test_leaderboard_combines_users(login, anon, neighborhoods):
    bob, alice = login('bob'), login('alice')
    lat, lon = TIMES_SQUARE
    tacos = save(bob, 'Los Tacos', lat=lat, lon=lon, rating=9)
    save(bob, "Joe's Pizza", lat=lat, lon=lon, rating=6)
    save(alice, 'los  tacos', lat=lat, lon=lon, rating=8)
    save(alice, 'Elsewhere', lat=40.6782, lon=-73.9442, rating=10)

    code = tacos['neighborhood']['code']
    response = anon.get(f'/neighborhoods/{code}/leaderboard')
    assert response.status_code == 200
    board = response.get_json()['restaurants']
    assert [(r['name'].lower(), r['ratings']) for r in board] == [
        ('los tacos', 2), ("joe's pizza", 1)]
    assert board[0]['average'] == 8.5
    assert board[0]['score'] > board[1]['score']
