# birria-taco

A geo-data REST API built with Flask-RESTX and MongoDB.

> Project idea is still being finalized. This README will be updated as the scope is defined.

## Team
- Krittika Garg
- Matthew Jiang
- (add teammates)

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
