# Using the Alpine variant — ~60% less memory than the full Kong image.
# This is critical for Railway's free/hobby tier memory limits.
FROM kong:3.4-alpine

USER root

# Install envsubst (gettext package on Alpine) for template rendering
RUN apk add --no-cache gettext

# Copy the Kong config template and the custom entrypoint
COPY kong.template.yml /usr/local/kong/kong.template.yml
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER kong

ENTRYPOINT ["/docker-entrypoint.sh"]
