import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

import pika
from pythonjsonlogger import jsonlogger

# --- Setup Logging ---
logger = logging.getLogger("analytics_service")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# --- Configuration ---
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE_NAME = "ecom.domain.events"
QUEUE_NAME = "analytics.events"
DB_PATH = os.getenv("DB_PATH", "analytics.db")


# --- Database Setup ---
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create daily_sales table if not exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_sales (
            date TEXT PRIMARY KEY,
            total_revenue REAL NOT NULL,
            order_count INTEGER NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def record_sale(amount: float):
    if amount is None:
        return

    today = datetime.utcnow().date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT total_revenue, order_count FROM daily_sales WHERE date = ?", (today,)
    )
    row = cursor.fetchone()

    if row:
        new_revenue = row[0] + amount
        new_count = row[1] + 1
        cursor.execute(
            "UPDATE daily_sales SET total_revenue = ?, order_count = ? WHERE date = ?",
            (new_revenue, new_count, today),
        )
    else:
        cursor.execute(
            "INSERT INTO daily_sales (date, total_revenue, order_count) VALUES (?, ?, ?)",
            (today, amount, 1),
        )

    conn.commit()
    conn.close()

    logger.info(f"Recorded sale of {amount}. Data updated for {today}.")


# --- RabbitMQ Connection ---
def get_connection():
    import time
    from urllib.parse import urlparse

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


def main():
    setup_db()
    logger.info("Starting Analytics Service...")

    connection = get_connection()
    channel = connection.channel()

    # Declare the topic exchange (should already exist, but good practice)
    channel.exchange_declare(
        exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
    )

    # Declare the queue for analytics
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    # Bind the queue to the exchange
    # We want to listen to order events
    routing_key = "order.*"
    channel.queue_bind(
        exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=routing_key
    )
    logger.info(f"Subscribed to {EXCHANGE_NAME} with routing_key '{routing_key}'")

    def callback(ch, method, properties, body):
        routing_key = method.routing_key
        try:
            event = json.loads(body.decode())
            logger.info(
                "Received event",
                extra={"event_routing_key": routing_key, "event_data": event},
            )

            if routing_key == "order.created":
                # Parse total amount
                total_str = event.get("total")
                total_amount = float(total_str) if total_str else 0.0

                record_sale(total_amount)

            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error(f"Failed to process event: {e}", exc_info=True)
            # Requeue if it's a transient failure, but for safety in this demo we'll ack it or nack without requeue
            # to prevent infinite loop of bad messages.
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

    logger.info("Waiting for events. To exit press CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Stopping Analytics Service...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
