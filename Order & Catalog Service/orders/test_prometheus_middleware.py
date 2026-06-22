"""
Tests for Prometheus middleware configuration.

Covers:
- PrometheusBeforeMiddleware is present as the first middleware
- PrometheusAfterMiddleware is present as the last middleware
- Both middleware are distinct (not duplicated)
- Metrics endpoint returns valid Prometheus format
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient


def test_prometheus_before_middleware_is_first():
    """PrometheusBeforeMiddleware must be the first entry in MIDDLEWARE."""
    assert settings.MIDDLEWARE[0] == (
        "django_prometheus.middleware.PrometheusBeforeMiddleware"
    )


def test_prometheus_after_middleware_is_last():
    """PrometheusAfterMiddleware must be the last entry in MIDDLEWARE."""
    assert settings.MIDDLEWARE[-1] == (
        "django_prometheus.middleware.PrometheusAfterMiddleware"
    )


def test_prometheus_middleware_are_not_duplicated():
    """
    The before and after middleware must be distinct classes.
    A common mistake is adding PrometheusBeforeMiddleware twice
    instead of PrometheusAfterMiddleware at the end.
    """
    before = "django_prometheus.middleware.PrometheusBeforeMiddleware"
    after = "django_prometheus.middleware.PrometheusAfterMiddleware"

    before_count = settings.MIDDLEWARE.count(before)
    after_count = settings.MIDDLEWARE.count(after)

    assert (
        before_count == 1
    ), f"PrometheusBeforeMiddleware appears {before_count} times, expected 1"
    assert (
        after_count == 1
    ), f"PrometheusAfterMiddleware appears {after_count} times, expected 1"


def test_both_prometheus_middleware_present():
    """Both before and after middleware must exist in MIDDLEWARE."""
    assert (
        "django_prometheus.middleware.PrometheusBeforeMiddleware" in settings.MIDDLEWARE
    )
    assert (
        "django_prometheus.middleware.PrometheusAfterMiddleware" in settings.MIDDLEWARE
    )


@pytest.mark.django_db
def test_metrics_endpoint_returns_prometheus_format():
    """
    The /metrics/django endpoint must return valid Prometheus text format.
    Presence of PrometheusAfterMiddleware is required for request metrics
    to be recorded.
    """
    client = APIClient()
    response = client.get("/metrics/django")
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "# HELP" in content
    assert "# TYPE" in content
    assert "django_http_requests_before_middlewares_total" in content
