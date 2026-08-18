#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker build -t artek-buddy-computer:local .
echo "built artek-buddy-computer:local"
