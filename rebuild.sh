#!/bin/bash
# Runs on PythonAnywhere (called by deploy.sh): pulls main, installs
# packages, and reloads the web app. Needs API_TOKEN set in ~/.bashrc.
set -eo pipefail

git pull origin main
source "/home/$PA_USER/.virtualenvs/$VENV/bin/activate"
pip install --upgrade -r requirements.txt
pa_reload_webapp.py "$PA_DOMAIN"
echo "Rebuilt $PA_DOMAIN"
