import json
import logging
from urllib.parse import urlparse

import pika
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Runs a placeholder RabbitMQ consumer to listen to Domain Events"

    def handle(self, *args, **options):
        broker_url = getattr(
            settings, "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
        )
        exchange_name = "ecom.domain.events"
        queue_name = "placeholder_analytics_queue"
        routing_key = "order.*"  # Listen to all order events

        self.stdout.write(
            self.style.SUCCESS(f"Starting placeholder consumer on {broker_url}")
        )

        try:
            parsed = urlparse(broker_url)
            credentials = pika.PlainCredentials(
                parsed.username or "guest", parsed.password or "guest"
            )
            parameters = pika.ConnectionParameters(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5672,
                credentials=credentials,
                virtual_host=(
                    "/"
                    if not parsed.path or parsed.path == "//"
                    else parsed.path.lstrip("/")
                ),
            )

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Ensure the exchange exists
            channel.exchange_declare(
                exchange=exchange_name, exchange_type="topic", durable=True
            )

            # Declare a persistent queue
            channel.queue_declare(queue=queue_name, durable=True)

            # Bind the queue to the exchange
            channel.queue_bind(
                exchange=exchange_name, queue=queue_name, routing_key=routing_key
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f" [*] Waiting for logs on {exchange_name} binding to {routing_key}. To exit press CTRL+C"
                )
            )

            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode("utf-8"))
                    self.stdout.write(
                        self.style.WARNING(
                            f"\n[x] Received Event: {method.routing_key}"
                        )
                    )
                    self.stdout.write(
                        self.style.NOTICE(
                            f"    Payload: {json.dumps(payload, indent=2)}"
                        )
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error parsing message: {e}"))

                # Acknowledge the message
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)

            channel.start_consuming()

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Consumer stopped."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Consumer error: {e}"))
