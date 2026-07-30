import os

# When running tests locally, PostgreSQL is reachable at localhost.
# In Docker, it's reachable at 'db' (the service name).
# CI sets POSTGRES_HOST explicitly via the workflow env vars.
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["REDIS_URL"] = "redis://localhost:6379/2"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minimum-32-chars-long")
os.environ.setdefault("INTERNAL_CLUSTER_SECRET", "test-internal-secret")
os.environ.setdefault("STRIPE_PUBLIC_KEY", "pk_test_placeholder")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_placeholder")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_event_publisher():
    """Mock the EventPublisher so tests don't try to connect to RabbitMQ."""
    with patch("config.events.publisher.publish") as mock_publish:
        yield mock_publish
