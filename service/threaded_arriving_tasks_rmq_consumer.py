import io, os
import logging
import asyncio
import traceback
import html
import json
from datetime import datetime
import uuid
from threading import Thread, Lock
from queue import Empty, Queue

from numpy import block
from thread_killer import ThreadKiller
from async_rabbitmq_consumer import ReconnectingRabbitMQConsumer
from async_rabbitmq_publisher import RabbitMQPublisher
from service_defs import EnsureDirectoryExists, DoesPathExistAndIsFile, DoesPathExistAndIsDirectory

import config
import tempfile
import base64
from minio import Minio
from minio.error import S3Error


def threaded_arriving_tasks_rmq_consumer(tokill,
                                         arriving_messages_queue,
                                         arriving_messages_queue_threading_lock):
    """Threaded worker for receiving the tasks from RabbitMQ messages.
    tokill is a thread_killer object that indicates whether a thread should be terminated
    arriving_tasks_queue is a limited size thread-safe Queue instance.
    """

    logger = logging.getLogger("arriving_tasks")
    logger.info("Thread for RabbitMQ consumer started")

    rmq_consumer = ReconnectingRabbitMQConsumer(arriving_messages_queue,
                                                arriving_messages_queue_threading_lock,
                                                logger)
    
    logger.info("Starting the RabbitMQ consumer")
    rmq_consumer.run()
    logger.info("Started the RabbitMQ consumer")
