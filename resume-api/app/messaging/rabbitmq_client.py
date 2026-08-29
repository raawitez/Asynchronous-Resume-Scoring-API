import os
import json
import pika
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

class RabbitMQPublisher:

    def __init__(self):
        self.connection = None
        self.channel    = None

    def _build_params(self):
        url = os.getenv("RABBITMQ_URL")
        if url:
            params = pika.URLParameters(url)
            params.socket_timeout = 5.0
            return params
        
        return pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            heartbeat=600,
            socket_timeout=5.0
        )

    def connect(self):
        try:
            self.connection = pika.BlockingConnection(self._build_params())
            self.channel = self.connection.channel()
            logger.info("RabbitMQ publisher connected successfully")
        except Exception as e:
            logger.warning(f"RabbitMQ connection failed: {e}")
            self.connection = None
            self.channel    = None

    def disconnect(self):
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("RabbitMQ disconnected")
        except Exception as e:
            logger.warning(f"RabbitMQ disconnect error: {e}")

    def publish(self, queue_name: str, event: dict) -> bool:
        if not self.connection or self.connection.is_closed or not self.channel or self.channel.is_closed:
            self.connect()

        if not self.channel:
            logger.warning(
                f"RabbitMQ unavailable — "
                f"skipping event: {event.get('event')}"
            )
            return False

        try:
            self.channel.queue_declare(
                queue=queue_name,
                durable=True   
            )
            self.channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps(event),
                properties=pika.BasicProperties(
                    delivery_mode=2   
                )
            )
            logger.info(
                f"[MQ] Published '{event.get('event')}' "
                f"resume_id={event.get('resume_id')}"
            )
            return True

        except Exception as e:
            logger.error(f"[MQ] Publish failed: {e}. Attempting reconnect.")
            self.connect()  
            return False


publisher = RabbitMQPublisher()