import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import pika
from django.core.management.base import BaseCommand
from django.db import transaction
from orders.models import Order

logger = logging.getLogger("saga_consumer")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

RABBITMQ_URL = os.environ.get(
    "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
)
EXCHANGE_NAME = "ecom.domain.events"
QUEUE_NAME = "saga.inventory.compensation"


class Command(BaseCommand):
    help = "Runs the RabbitMQ consumer for Saga Compensating Transactions"

    def get_connection(self):
        parsed = urlparse(RABBITMQ_URL)
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

        for _ in range(5):
            try:
                return pika.BlockingConnection(parameters)
            except Exception as e:
                logger.warning(f"Connection failed, retrying in 5 seconds... ({e})")
                time.sleep(5)

        logger.error("Could not connect to RabbitMQ after multiple retries.")
        sys.exit(1)

    def on_message(self, channel, method, properties, body):
        try:
            event = json.loads(body)
            routing_key = method.routing_key
            logger.info(f"Received event: {routing_key}")

            if routing_key == "payment.failed":
                order_id = event.get("order_id")
                if not order_id:
                    logger.warning(
                        "No order_id in payment.failed event. Cannot compensate."
                    )
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    return

                try:
                    with transaction.atomic():
                        order = Order.objects.get(id=order_id)
                        if order.status == "pending":
                            logger.info(
                                f"Compensating transaction for Order {order.id}. Restoring inventory..."
                            )
                            order.status = "canceled"
                            order.save()

                            # Restore inventory
                            for item in order.items.all():
                                product = item.product
                                product.stock += item.quantity
                                product.save()
                                logger.info(
                                    f"Restored {item.quantity} units of {product.name}"
                                )
                        else:
                            logger.info(
                                f"Order {order.id} is already {order.status}. No compensation needed."
                            )
                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found during compensation.")

            # Acknowledge
            if not channel._impl.is_closed:
                channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error(f"Error processing saga message: {str(e)}", exc_info=True)
            # Route to DLX
            if not channel._impl.is_closed:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def handle(self, *args, **options):
        logger.info("Starting Saga Consumer...")
        connection = self.get_connection()
        channel = connection.channel()

        channel.exchange_declare(
            exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
        )

        # DLX setup for Saga
        channel.exchange_declare(
            exchange="ecom.dlx", exchange_type="direct", durable=True
        )
        channel.queue_declare(queue="saga.dlq", durable=True)
        channel.queue_bind(
            exchange="ecom.dlx", queue="saga.dlq", routing_key=QUEUE_NAME
        )

        arguments = {
            "x-dead-letter-exchange": "ecom.dlx",
            "x-dead-letter-routing-key": QUEUE_NAME,
        }

        channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments=arguments)
        channel.queue_bind(
            exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key="payment.failed"
        )

        logger.info(f"Subscribed to {EXCHANGE_NAME} with routing_key 'payment.failed'")

        channel.basic_consume(
            queue=QUEUE_NAME, on_message_callback=self.on_message, auto_ack=False
        )

        try:
            logger.info("Waiting for saga events. To exit press CTRL+C")
            channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            channel.stop_consuming()
        finally:
            connection.close()
