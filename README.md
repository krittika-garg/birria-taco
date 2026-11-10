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
The API will be available at http://127.0.0.1:8000. Opening that URL in a browser
shows a Swagger page for trying the endpoints. To call one that needs a login,
click **Authorize** and enter `Bearer YOUR_ACCESS_TOKEN`.

### Use MongoDB locally
Start MongoDB in Docker (needs Docker Desktop with WSL integration turned on), or
install MongoDB Community and run `mongod` instead:
~~~
make mongo
~~~
With the virtualenv active, load the states and NYC neighborhoods:
~~~
make seed
~~~
`./local.sh` then uses local Mongo by default. To use the cloud instead, set
`CLOUD_MONGO=1` and `MONGO_URI` in `.env`. For a non-default host or port, set
`MONGO_LOCAL_URI`.

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
The response contains `access_token`, `refresh_token`, `token_type` (`Bearer`),
and `expires_in` (900 seconds). Include the access token on all restaurant
requests:

~~~text
Authorization: Bearer YOUR_ACCESS_TOKEN
~~~

Missing, invalid, or expired tokens return `401`. Session cookies alone no
longer authorize restaurant requests. Missing JWT configuration returns `503`
when issuing a token or validating a supplied Bearer token.

Access tokens expire after 15 minutes. To stay logged in, send
`POST /refresh` with JSON `{"refresh_token": "..."}` when a request returns
`401`, then retry that request. The response has the same fields as `/login`.
Refresh tokens last 7 days and work once: every refresh returns a new one, so
always store the latest, and an invalid, expired, or reused token returns `401`,
meaning the user must log in again. A frontend should only run one refresh at a
time, because a second request with the same token will fail.

On logout, send `POST /logout` with JSON `{"refresh_token": "..."}` to revoke
the refresh token, and discard both tokens. An access token that was already
issued keeps working until it expires.

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

`GET`, `PUT`, and `DELETE` on `/restaurants/<id>` return `404` for an `id`
that doesn't exist or belongs to another user. Ownership comes from the verified JWT; a supplied `user`
field cannot change it. Each saved entry is personal, and repeated entries
are allowed. Comparison-based ranking and a shared restaurant catalog are not implemented
yet.

## Group mode

Groups let friends decide where to eat together. A group lasts 2 hours.
All group endpoints need an access token.

- `POST /groups` starts a group with you as host and only member, and returns
  `201` with `{"group": {...}}`. Share its `invite_token` with friends.
- `POST /groups/join/<invite_token>` adds you to the group and returns
  `{"group": {...}}`. Joining twice is harmless.
- `GET /groups/<id>` returns `{"group": {...}}` if you are a member.

All three return `404` for an expired group or a bad token, and `GET` also
returns `404` to non-members. Voting and live updates are not implemented yet.
