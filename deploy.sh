#!/bin/bash
# Deploys to PythonAnywhere: SSHes in and runs rebuild.sh there.
set -euo pipefail

: "${PA_USER:?Set PA_USER to the PythonAnywhere username}"
: "${PA_PASSWORD:?Set PA_PASSWORD to the PythonAnywhere password}"
PROJ_DIR=${PROJ_DIR:-birria-taco}
VENV=${VENV:-birria-taco}
PA_DOMAIN=${PA_DOMAIN:-$PA_USER.pythonanywhere.com}

echo "Deploying to $PA_DOMAIN"
# -e reads the password from SSHPASS, so it stays out of the process list.
SSHPASS=$PA_PASSWORD sshpass -e ssh -o StrictHostKeyChecking=no \
    "$PA_USER@ssh.pythonanywhere.com" <<REMOTE
cd ~/$PROJ_DIR && PA_USER=$PA_USER VENV=$VENV PA_DOMAIN=$PA_DOMAIN ./rebuild.sh
REMOTE
