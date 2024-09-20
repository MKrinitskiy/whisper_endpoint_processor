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


def reporting_messaging_thread(tokill: ThreadKiller,
                               reporting_messages_queue: Queue,
                               reporting_messages_queue_threading_lock: Lock):
    """Threaded worker for sending the tasks from departing_tasks_queue to RabbitMQ messages.
    tokill is a thread_killer object that indicates whether a thread should be terminated
    departing_tasks_queue is a limited size thread-safe Queue instance.
    """
    reporting_messaging_thread_logger = logging.getLogger("reporting_messaging_thread_logger")
    reporting_messaging_thread_logger.info("Threaded reporting messages RabbitMQ feeder started")

    rmq_publisher = RabbitMQPublisher(reporting_messages_queue,
                                      reporting_messages_queue_threading_lock,
                                      reporting_messaging_thread_logger)
    rmq_publisher.run()

    reporting_messaging_thread_logger.info("rmq_publisher exiting")
