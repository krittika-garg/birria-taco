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
On Windows, run these commands in Git Bash (it comes with Git) or WSL.
~~~
python3 -m venv venv        # Windows: py -m venv venv
source venv/bin/activate    # Windows Git Bash: source venv/Scripts/activate
pip install -r requirements-dev.txt
cp .env.example .env
~~~
Then fill in `JWT_SECRET_KEY` in `.env`; the file shows how to generate one.
Activate the virtualenv again in each new terminal.

The `make` targets below work on macOS and WSL. Git Bash has no `make`; install
it with `winget install ezwinports.make`, or run the plain commands instead.

### Run the tests
~~~
make all_tests    # or: pytest
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

### Back up and restore the database
`data/bkup.sh` saves every collection to `data/bkup/` (gitignored), and
`data/restore.sh` puts them back, replacing what's there. Both need the
[MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools)
and use `MONGO_URI` from `.env`. To target local Mongo instead, run
`MONGO_URI=mongodb://localhost:27017/ data/bkup.sh`.

### Where endpoints live
Each feature has its own module in `server/` (`accounts.py`, `restaurants.py`,
`states.py`, `neighborhoods.py`, ...) with its own Flask-RESTX `Namespace`, and
its own test file in `server/tests/`. `server/endpoints.py` only creates the app
and registers each namespace. Add a new feature as a new module rather than
growing an existing one.

### Deploy
The live database is a free M0 cluster on MongoDB Atlas, in the `birria-taco`
organization (ask Sihan for an invite). The app connects as the `birria-app`
user, which can only read and write `seDB`. Tests write to other databases, so
run them against local Mongo, not Atlas. Network access is open to `0.0.0.0/0`
because PythonAnywhere has no fixed IP. To point your local server at Atlas,
set `CLOUD_MONGO=1` and `MONGO_URI` in `.env`; quote the URI, since `local.sh`
reads `.env` as a bash script.

The API runs on PythonAnywhere, which needs a paid account: free accounts
can't reach Atlas. To set it up:
1. In a PA Bash console: clone the repo, then
   `mkvirtualenv birria-taco --python=python3.13` and
   `pip install -r requirements.txt`.
2. Web tab: add a new web app with **Manual configuration**, then set its
   virtualenv to `birria-taco`.
3. Replace the WSGI configuration file with
   [pythonanywhere_wsgi.py](pythonanywhere_wsgi.py) and fill in its
   placeholders.
4. Reload, then open `/health`. It should return
   `{"db": "ok", "mode": "cloud"}`; if not, check the error log.

After that, `deploy.sh` redeploys by SSHing in and running `rebuild.sh`
there, which pulls `main` and reloads the site. It needs `PA_USER` and
`PA_PASSWORD` set.

## Personal restaurant list

Set a private `JWT_SECRET_KEY` in your gitignored `.env` before starting
the server with `./local.sh`. Use a randomly generated key of at least 32 bytes.
For deployment, configure a persistent key in the hosting environment.

Sign up through `POST /register` or log in through `POST /login`, both with JSON
`{"username": "...", "password": "..."}`. Signing up also logs the new user in.
Both responses contain `access_token`, `refresh_token`, `token_type` (`Bearer`),
and `expires_in` (900 seconds). `/register` returns `201`, or `409` if the
username is taken. Include the access token on all restaurant requests:

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
the refresh token, and discard both tokens. To log out on every device, send
`POST /logout/all` with the access token; it revokes all of that user's refresh
tokens and returns how many with `sessions_ended`. Either way, an access token
that was already issued keeps working until it expires.

- `POST /restaurants` saves an entry to the logged-in user's list and returns
  `201` with `{"restaurant": {...}}`. Send a JSON object with nonblank `name` and
  `city` strings. `cuisine` and `notes` are optional strings, defaulting to empty.
  `rating` is an optional number from 0 to 10, defaulting to `null`.
  Text is trimmed; invalid input returns `400`.
- `GET /restaurants` returns `{"restaurants": [...]}` containing only the
  logged-in user's entries, or an empty list, sorted by `rating` (highest
  first, unrated last). Entries include a string `_id`.
  Optional filters combine: `q` matches part of the name, `cuisine` matches
  the full cuisine (both case-insensitive), and `min_rating` accepts 0–10,
  excluding unrated entries. Blank text filters are ignored; invalid minimum
  ratings return `400`. Example: `/restaurants?q=ramen&cuisine=Japanese&min_rating=8`.
  Filter by `status=want_to_try` or `status=visited`; omit it to return both.
  `borough` (case-insensitive, e.g. `/restaurants?borough=Brooklyn`) comes from
  the neighborhood the entry's `lat`/`lon` falls in, so entries without a
  location never match.
- `GET /restaurants/<id>` returns `{"restaurant": {...}}` for one of the
  logged-in user's entries.
- `PUT /restaurants/<id>` updates one of the logged-in user's entries using
  the same validation as `POST`, and returns `200` with `{"restaurant": {...}}`.
- `DELETE /restaurants/<id>` removes one of the logged-in user's entries and
  returns `200`. It also leaves your ranked list, and any ranking in
  progress has to start again (`409`).

To save a place for later, include `"status": "want_to_try"` in the POST
body, with no rating. After visiting, PUT the restaurant's name, city and
other desired fields with `"status": "visited"` and an optional rating.
POST and PUT default omitted status to `visited`; existing records without
status are also treated as visited. Unknown statuses and ratings on
want-to-try entries return `400`. Want-to-try entries remain unrated and
are excluded by `min_rating`, including `min_rating=0`.

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
- `GET /rankings` returns `{"rankings": [...]}`, your list best first. Each
  entry has `restaurant_id`, `bucket`, `ranked_at` and a 0-10 `score`.

A place's `score` comes from its position: each bucket spreads its places
evenly over a band (`liked` 6.7-10, `fine` 3.4-6.6, `disliked` 0-3.3), best
first, so scores shift as you rank more places. It is separate from the
manual `rating` on `/restaurants`, which you set yourself.

Every `better`/`worse` answer is also stored in `comparisons` for the city
leaderboard. Not yet: re-ranking a place already in your list.

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
- `GET /groups` returns `{"groups": [...]}` with the live groups you are a
  member of, newest first.

`GET /groups/<id>` and both `POST`s return `404` for an expired group or a bad
token, and `GET` also
returns `404` to non-members.

### Voting

Each member gets one vote, for any restaurant that someone in the group has
saved. Votes go away when the group expires. Both endpoints return `404` to
non-members and for expired groups.

- `PUT /groups/<id>/vote` with `{"restaurant_id": "..."}` casts your vote, or
  replaces your earlier vote, and returns `{"vote": {"restaurant_id": "..."}}`.
  It returns `400` without a `restaurant_id`, and `404` if no member has saved
  that restaurant.
- `GET /groups/<id>/votes` returns
  `{"tally": [{"restaurant_id", "name", "votes"}], "my_vote", "voted", "members"}`,
  with the most votes first and ties sorted by name. It doesn't show who voted
  for what. Votes from people who left the group, and votes for restaurants
  that have since been deleted, are not counted.

Live updates are not implemented yet.

## Following users

All follow endpoints need an access token.

- `POST /users/<username>/follow` follows a user. Following someone twice is
  harmless. It returns `400` for yourself and `404` for an unknown user.
- `DELETE /users/<username>/follow` unfollows a user. Unfollowing someone you
  don't follow is harmless.
- `GET /users/<username>/followers` returns `{"followers": [...]}`, the sorted
  usernames following that user.
- `GET /users/<username>/following` returns `{"following": [...]}`, the sorted
  usernames that user follows.

Both lists return `404` for an unknown user.
