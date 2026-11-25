"""
Template for the PythonAnywhere WSGI file. Don't edit it here: on PA, open
Web tab -> WSGI configuration file, replace its contents with this, fill in
the placeholders, and click Reload. Secrets live only in PA's copy.
"""
import os
import sys

PROJECT_DIR = '/home/<pa-user>/birria-taco'
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ['CLOUD_MONGO'] = '1'
# From Atlas: Clusters -> Connect -> Drivers -> Python, as the birria-app user.
os.environ['MONGO_URI'] = '<atlas connection string>'
# Generate each with: python -c "import secrets; print(secrets.token_hex(32))"
os.environ['JWT_SECRET_KEY'] = '<random key>'
os.environ['SECRET_KEY'] = '<random key>'

from server.endpoints import create_app  # noqa: E402

application = create_app()
