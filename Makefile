# Generate kong.yml from template using the JWT_SECRET from your .env
kong-config:
	@KONG_JWT_SECRET=$$(grep '^JWT_SECRET' .env | cut -d '=' -f2) && \
	export KONG_JWT_SECRET && \
	envsubst '$$KONG_JWT_SECRET' < gateway/kong.template.yml > gateway/kong.yml
	@echo "✅ gateway/kong.yml generated from template"

# Regenerate and restart gateway only
kong-reload: kong-config
	docker-compose restart gateway
	@echo "✅ Kong restarted with new config"
