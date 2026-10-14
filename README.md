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

Log in through `POST /login` and include the returned session cookie on requests
to `/restaurants` and `/restaurants/<id>`. All of them return `401` when
logged out.

- `POST /restaurants` saves an entry to the logged-in user's list and returns
  `201` with `{"restaurant": {...}}`. Send a JSON object with nonblank `name` and
  `city` strings. `cuisine` and `notes` are optional strings, defaulting to empty.
  `rating` is an optional number from 0 to 10, defaulting to `null`.
  Text is trimmed; invalid input returns `400`.
- `GET /restaurants` returns `{"restaurants": [...]}` containing only the
  logged-in user's entries, or an empty list, highest `rating` first with
  unrated entries last. Entries include a string `_id`.
- `GET /restaurants/<id>` returns `{"restaurant": {...}}` for one of the
  logged-in user's entries.
- `PUT /restaurants/<id>` updates one of the logged-in user's entries using
  the same validation as `POST`, and returns `200` with `{"restaurant": {...}}`.
- `DELETE /restaurants/<id>` removes one of the logged-in user's entries and
  returns `200`.

`GET`, `PUT` and `DELETE` on `/restaurants/<id>` return `404` for an `id`
that doesn't exist or belongs to another user. Ownership comes from the session; a supplied `user`
field cannot change it. Each saved entry is personal, and repeated entries
are allowed. Head-to-head ranking and a shared restaurant catalog are not
implemented yet.
