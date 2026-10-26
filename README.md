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
- `PUT /restaurants/<id>` updates one of the logged-in user's entries using
  the same validation as `POST`, and returns `200` with `{"restaurant": {...}}`.
- `DELETE /restaurants/<id>` removes one of the logged-in user's entries and
  returns `200`.

Both `PUT` and `DELETE` return `404` for an `id` that doesn't exist or
belongs to another user. Ownership comes from the verified JWT; a supplied `user`
field cannot change it. Each saved entry is personal, and repeated entries
are allowed. Comparison-based ranking and a shared restaurant catalog are not implemented
yet.
