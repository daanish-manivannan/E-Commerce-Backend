import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import pika
from dotenv import load_dotenv
from pythonjsonlogger import jsonlogger

# Load env variables
load_dotenv()

# Configure structured JSON logging
logger = logging.getLogger("notification_service")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//")
EXCHANGE_NAME = "ecom.domain.events"
QUEUE_NAME = "notification.events"


def get_connection():
    parsed = urlparse(RABBITMQ_URL)
    credentials = pika.PlainCredentials(
        parsed.username or "guest", parsed.password or "guest"
    )
    parameters = pika.ConnectionParameters(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5672,
        credentials=credentials,
        virtual_host=(
            "/" if not parsed.path or parsed.path == "//" else parsed.path.lstrip("/")
        ),
    )

    # Retry mechanism for initial connection
    for _ in range(5):
        try:
            return pika.BlockingConnection(parameters)
        except Exception as e:
            logger.warning(f"Connection failed, retrying in 5 seconds... ({e})")
            time.sleep(5)

    logger.error("Could not connect to RabbitMQ after multiple retries.")
    sys.exit(1)


def on_message(channel, method, properties, body):
    try:
        event = json.loads(body)
        routing_key = method.routing_key

        logger.info(f"Received event: {routing_key}", extra={"event_data": event})

        if routing_key == "order.created":
            order_id = event.get("order_id")
            user_id = event.get("user_id")
            total_amount = event.get("total")
            # Simulate sending an email
            logger.info(
                f"Simulating order confirmation email for order {order_id} (User: {user_id}, Total: {total_amount})"
            )
        elif routing_key == "inventory.low":
            product_name = event.get("product_name")
            available = event.get("available_stock")
            logger.warning(
                f"ALERT: Low stock for '{product_name}'. Only {available} remaining."
            )
        elif routing_key == "inventory.out_of_stock":
            product_name = event.get("product_name")
            logger.warning(f"CRITICAL: '{product_name}' is completely OUT OF STOCK!")
        else:
            logger.info(f"Ignoring unhandled event type: {routing_key}")

    except Exception as e:
        logger.error(
            "Error processing message",
            extra={"error": str(e), "body": body.decode("utf-8")},
        )
        # Nack without requeue sends it to the DLX
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    finally:
        # Acknowledge the message if it was processed successfully
        if not channel._impl.is_closed:
            channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
    logger.info("Starting Notification Service...")
    connection = get_connection()
    channel = connection.channel()

    # Ensure the exchange exists (in case this starts before the publisher)
    channel.exchange_declare(
        exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
    )

    # Set up Dead Letter Exchange and Queue
    channel.exchange_declare(exchange="ecom.dlx", exchange_type="direct", durable=True)
    channel.queue_declare(queue="notification.dlq", durable=True)
    channel.queue_bind(exchange="ecom.dlx", queue="notification.dlq", routing_key=QUEUE_NAME)

    # Declare the queue with DLX arguments
    arguments = {
        "x-dead-letter-exchange": "ecom.dlx",
        "x-dead-letter-routing-key": QUEUE_NAME
    }
    channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments=arguments)

    # Bind the queue to the exchange
    # We want to listen to order and inventory events
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key="order.*")
    channel.queue_bind(
        exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key="inventory.*"
    )

    logger.info(
        f"Subscribed to {EXCHANGE_NAME} with routing_keys 'order.*' and 'inventory.*'"
    )

    channel.basic_consume(
        queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=False
    )

    try:
        logger.info("Waiting for events. To exit press CTRL+C")
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
