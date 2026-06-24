FROM kong:3.4

USER root

# Install envsubst (from gettext-base) so we can render kong.template.yml
# with the KONG_JWT_SECRET at container startup — keeping secrets out of the repo.
RUN apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

# Copy the Kong config template and the custom entrypoint
COPY kong.template.yml /usr/local/kong/kong.template.yml
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER kong

ENTRYPOINT ["/docker-entrypoint.sh"]
