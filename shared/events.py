import json
import pika
from .config import config

class EventBus:
    def __init__(self):
        self.connection = None
        self.channel = None
        # Don't connect automatically - connect when needed
    
    def connect(self):
        if self.connection and not self.connection.is_closed:
            return  # Already connected
            
        credentials = pika.PlainCredentials(
            config.get('rabbitmq', 'username'),
            config.get('rabbitmq', 'password')
        )
        parameters = pika.ConnectionParameters(
            host=config.get('rabbitmq', 'host'),
            port=config.getint('rabbitmq', 'port'),
            virtual_host=config.get('rabbitmq', 'vhost'),
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        # Declare exchange
        self.channel.exchange_declare(exchange='webradio9', exchange_type='topic')
    
    def publish(self, routing_key, message):
        self.connect()  # Ensure connection before publishing
        self.channel.basic_publish(
            exchange='webradio9',
            routing_key=routing_key,
            body=json.dumps(message)
        )
    
    def subscribe(self, routing_key, callback):
        self.connect()  # Ensure connection before subscribing
        result = self.channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue
        
        self.channel.queue_bind(exchange='webradio9', queue=queue_name, routing_key=routing_key)
        
        def wrapper(ch, method, properties, body):
            message = json.loads(body)
            callback(message)
        
        self.channel.basic_consume(queue=queue_name, on_message_callback=wrapper, auto_ack=True)
    
    def start_consuming(self):
        self.channel.start_consuming()

# Global event bus instance
event_bus = EventBus()
