# birria-taco

[![CI](https://github.com/krittika-garg/birria-taco/actions/workflows/main.yml/badge.svg)](https://github.com/krittika-garg/birria-taco/actions/workflows/main.yml)

A restaurant-ranking app in the spirit of Beli: users log places they've eaten,
rank them against each other, and discover spots through friends. The backend is a
REST API built with Flask-RESTX and MongoDB.

> Scope is still being fleshed out; planned features will be tracked in issues.

## Team
- Krittika Garg
- Matthew Jiang
- Daniel Enriquez
- Anuraghav Padmaprasad
- Sihan Ma

## Getting Started

### Set up the dev environment
~~~
make dev_env
source venv/bin/activate
~~~

If you get `ModuleNotFoundError: No module named 'server'`, set your PYTHONPATH to the repo root:
~~~
export PYTHONPATH=$(pwd)
~~~

### Run the tests
~~~
make all_tests
~~~

### Run the server locally
~~~
./local.sh
~~~
The API will be available at http://127.0.0.1:8000.

### Where endpoints live
Each feature has its own module in `server/` (`accounts.py`, `restaurants.py`,
`states.py`, `neighborhoods.py`, ...) with its own Flask-RESTX `Namespace`, and
its own test file in `server/tests/`. `server/endpoints.py` only creates the app
and registers each namespace. Add a new feature as a new module rather than
growing an existing one.

### Build for production
~~~
make prod
~~~

## Personal restaurant list

Set a private `JWT_SECRET_KEY` in your gitignored `.env` before starting
the server with `./local.sh`. Use a randomly generated key of at least 32 bytes.
For deployment, configure a persistent key in the hosting environment.

Log in through `POST /login` with JSON `{"username": "...", "password": "..."}`.
The response contains `access_token`, `token_type` (`Bearer`), and
`expires_in` (900 seconds). Include the token on all restaurant requests:

~~~text
Authorization: Bearer YOUR_ACCESS_TOKEN
~~~

Missing, invalid, or expired tokens return `401`. Session cookies alone no
longer authorize restaurant requests. Missing JWT configuration returns `503`
when issuing a token or validating a supplied Bearer token.

Tokens expire after 15 minutes. Refresh tokens are not implemented yet.
On logout, the frontend must discard its token. `POST /logout` clears legacy
session data but does not revoke an issued JWT.

- `POST /restaurants` saves an entry to the logged-in user's list and returns
  `201` with `{"restaurant": {...}}`. Send a JSON object with nonblank `name` and
  `city` strings. `cuisine` and `notes` are optional strings, defaulting to empty.
  `rating` is an optional number from 0 to 10, defaulting to `null`.
  Text is trimmed; invalid input returns `400`.
- `GET /restaurants` returns `{"restaurants": [...]}` containing only the
  logged-in user's entries, or an empty list, sorted by `rating` (highest
  first, unrated last). Entries include a string `_id`.
- `GET /restaurants/<id>` returns `{"restaurant": {...}}` for one of the
  logged-in user's entries.
- `PUT /restaurants/<id>` updates one of the logged-in user's entries using
  the same validation as `POST`, and returns `200` with `{"restaurant": {...}}`.
- `DELETE /restaurants/<id>` removes one of the logged-in user's entries and
  returns `200`.

## Ranking a restaurant

Ranking places one of your saved restaurants into your list by asking
"which was better?" a few times (a binary search, so about log2 of the
bucket's size). Your list is ordered best first: `liked`, then `fine`,
then `disliked`. Both endpoints need the Bearer token.

- `POST /rank-sessions` with `{"restaurant_id": "...", "bucket": "liked"}`
  starts a session and returns `201`. If that bucket is empty the place is
  saved straight away: `{"done": true, "position": 0}`. Otherwise the response
  is `{"done": false, "session_id": "...", "compare": {restaurant}}`.
  Unknown or another user's restaurant returns `404`; one already in your
  list returns `409`.
- `POST /rank-sessions/<session_id>/answer` with `{"answer": "better"}`
  says whether the new place is `better` or `worse` than `compare`, or
  `same` to put it right there. Returns the next `compare`, or
  `{"done": true, "position": n}` once it is saved (`n` counts from 0 across
  the whole list). Sessions expire after 15 minutes (`404`).

Every `better`/`worse` answer is also stored in `comparisons` for the city
leaderboard. Not yet: re-ranking a place already in your list, an endpoint to
read your ranked list, and protection against two tabs ranking at once.

`GET`, `PUT`, and `DELETE` on `/restaurants/<id>` return `404` for an `id`
that doesn't exist or belongs to another user. Ownership comes from the verified JWT; a supplied `user`
field cannot change it. Each saved entry is personal, and repeated entries
are allowed. Comparison-based ranking and a shared restaurant catalog are not implemented
yet.
