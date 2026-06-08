# Secrets Management

## Secrets in This Project

| Secret | Used By | Purpose |
|--------|---------|---------|
| `JWT_SECRET` | FastAPI + Kong | Signs and verifies all access tokens |
| `SECRET_KEY` | Django | CSRF, sessions, signed URLs |
| `INTERNAL_CLUSTER_SECRET` | FastAPI → Django | Internal service-to-service auth |
| `STRIPE_SECRET_KEY` | Django | Stripe API calls |
| `STRIPE_WEBHOOK_SECRET` | Django | Verifies Stripe webhook payloads |
| `POSTGRES_PASSWORD` | All services | Database access |

---

## Generating New Secrets

```bash
# JWT_SECRET and INTERNAL_CLUSTER_SECRET
python -c "import secrets; print(secrets.token_hex(32))"

# Django SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(50))"

# POSTGRES_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Rotating JWT_SECRET

JWT_SECRET is shared between FastAPI and Kong. Both must be updated together.

1. Generate a new secret:
```bash
   python -c "import secrets; print(secrets.token_hex(32))"
```
2. Update `JWT_SECRET` in `.env`
3. Regenerate `kong.yml` and restart:
```bash
   make kong-reload
```
4. All existing access tokens become invalid immediately. Users must log in again.
5. Refresh tokens are unaffected — they are opaque random values, not JWTs.

**Zero-disruption option:** Add a second Kong consumer with the new secret temporarily.
Old tokens (max 15 min lifetime) expire naturally. Then remove the old consumer.

---

## Rotating INTERNAL_CLUSTER_SECRET

1. Generate a new value
2. Update `.env`
3. Restart both services:
```bash
   docker-compose restart identity_service order-service
```
4. Sync calls will fail for the few seconds between restarts — this is acceptable.

---

## Rotating Django SECRET_KEY

Invalidates all Django sessions, CSRF tokens, and pending password-reset URLs.

1. Generate a new value
2. Update `.env`
3. Restart:
```bash
   docker-compose restart order-service order_worker order_beat
```
4. Kong JWT auth is unaffected — it uses `JWT_SECRET`, not `SECRET_KEY`.

---

## Rotating Stripe Keys

1. Roll the key in Stripe Dashboard → Developers → API Keys
2. Update `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`
3. Restart Django:
```bash
   docker-compose restart order-service
```

---

## Known Git History Exposure

The following values were committed to git history and must be treated
as compromised before any production deployment:

- Kong JWT secret: `10633b0564498e9d489b479d8e52a5bb75f4ecf68bc6f0bd6b57cbd4f4e070b9`
- Stripe test-key strings in older README versions

Action: rotate all of the above before production. Never reuse committed values.

---

## Pre-Production Checklist

- [ ] `JWT_SECRET` rotated, not the committed dev value
- [ ] `SECRET_KEY` rotated, not a placeholder
- [ ] `INTERNAL_CLUSTER_SECRET` rotated
- [ ] `POSTGRES_PASSWORD` not the default `ecom_password`
- [ ] `STRIPE_SECRET_KEY` starts with `sk_live_`
- [ ] `STRIPE_WEBHOOK_SECRET` starts with `whsec_`
- [ ] `.env` is in `.gitignore` and never committed
- [ ] `gateway/kong.yml` is in `.gitignore`
- [ ] `gateway/kong.yml` generated from `kong.template.yml` at deploy time
