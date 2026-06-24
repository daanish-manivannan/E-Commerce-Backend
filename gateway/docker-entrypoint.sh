#!/bin/sh
set -e

# Render the Kong declarative config from the template.
# KONG_JWT_SECRET is injected as a Railway environment variable — never stored in the repo.
envsubst '$KONG_JWT_SECRET' < /usr/local/kong/kong.template.yml > /usr/local/kong/kong.yml

echo "✅ Kong config generated from template (KONG_JWT_SECRET injected)"

# Hand off to Kong's official docker-start command
exec kong docker-start
