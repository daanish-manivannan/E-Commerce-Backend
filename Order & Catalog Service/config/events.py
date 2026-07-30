import json
import logging
from urllib.parse import urlparse

import pika
from django.conf import settings

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Publishes domain events to RabbitMQ using standard AMQP protocol.
    This ensures events are decoupled from Celery and can be consumed
    by microservices written in any language.
    """

    def __init__(self, exchange_name="ecom.domain.events"):
        self.exchange_name = exchange_name
        self.broker_url = getattr(
            settings, "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
        )
        self._connection = None
        self._channel = None

    def _connect(self):
        try:
            # Parse the AMQP URL
            parsed = urlparse(self.broker_url)

            # Pika's URL parameters handler doesn't perfectly handle Django's default
            # Celery broker URLs with double slashes (//) at the end, so we parse manually
            credentials = pika.PlainCredentials(
                parsed.username or "guest", parsed.password or "guest"
            )
            parameters = pika.ConnectionParameters(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5672,
                credentials=credentials,
                # Use standard virtual host if it ends with //, otherwise parse the path
                virtual_host=(
                    "/"
                    if not parsed.path or parsed.path == "//"
                    else parsed.path.lstrip("/")
                ),
            )

            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()

            # Declare a topic exchange. Topic allows wildcard routing keys like `order.*`
            self._channel.exchange_declare(
                exchange=self.exchange_name, exchange_type="topic", durable=True
            )
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ for EventPublisher: {e}")
            self._connection = None
            self._channel = None

    def publish(self, routing_key: str, payload: dict):
        """
        Publishes a JSON payload to the domain events exchange.
        """
        try:
            if not self._connection or self._connection.is_closed:
                self._connect()

            if self._channel and self._channel.is_open:
                message_body = json.dumps(payload)
                self._channel.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=routing_key,
                    body=message_body,
                    properties=pika.BasicProperties(
                        delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                        content_type="application/json",
                    ),
                )
                logger.info(
                    f"Published Domain Event [{routing_key}] to exchange {self.exchange_name}"
                )
            else:
                logger.error(
                    f"Could not publish Domain Event [{routing_key}]: No active RabbitMQ connection."
                )
        except Exception as e:
            logger.error(
                f"Exception while publishing Domain Event [{routing_key}]: {e}"
            )
            # Try to forcefully close so it reconnects next time
            if self._connection and not self._connection.is_closed:
                try:
                    self._connection.close()
                except Exception:
                    pass


# Singleton instance to be imported and used across the app
publisher = EventPublisher()
