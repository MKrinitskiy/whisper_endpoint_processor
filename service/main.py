from asyncio import tasks
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
from threaded_arriving_tasks_rmq_consumer import threaded_arriving_tasks_rmq_consumer
from received_messages_processor import received_messages_processor
from reporting_messaging_thread import reporting_messaging_thread


# setup
reporting_messages_queue = Queue(maxsize=1024)
reporting_messages_queue_threading_lock = Lock()
arriving_messages_queue = Queue(maxsize=1024)
arriving_messages_queue_threading_lock = Lock()
departing_thread_killer = ThreadKiller()
departing_thread_killer.set_tokill(False)
arriving_thread_killer = ThreadKiller()
arriving_thread_killer.set_tokill(False)

EnsureDirectoryExists('./logs')
logging.basicConfig(filename='./logs/service.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%dT%H:%M:%S')
logger = logging.getLogger(__name__)

#region minio setup
logger.info("Connecting to minio...")
try:
    s3 = Minio(f"{os.getenv('MINIO_HOSTNAME', 'default_hostname')}:{os.getenv('MINIO_PORT', '9000')}",
            access_key=os.getenv('MINIO_ACCESS_KEY', 'default_access_key'),
            secret_key=os.getenv('MINIO_SECRET_KEY', 'default_secret_key'),
            secure=False
        )
    logger.info("Connected to minio.")
except Exception as e:
    logger.error("Failed to connect to minio.")
    logger.error(e)
    exit(1)

logger.info("Checking if bucket exists...")
bucket_name = os.getenv('MINIO_BUCKET_NAME', 'whisper_telegram_bot')
try:
    if not s3.bucket_exists(bucket_name):
        logger.error(f"Bucket {bucket_name} does not exist. Will not be able to retrieve task files.")
        exit(1)
    else:
        logger.info(f"Bucket {bucket_name} found successfully.")
except Exception as e:
    logger.critical(f"Object storage not reachable")
    logger.error(e)
    exit(1)
logger.info("Bucket check complete.")
#endregion


user_semaphores = {}
user_tasks = {}



def main():
    logger.info("Starting service.")

    #region arriving_messages_thread
    # this thread reads the messages arriving from RabbitMQ
    logger.info("Starting the thread to read incoming messages that describe tasks.")
    arriving_messages_thread = Thread(target=threaded_arriving_tasks_rmq_consumer,
                                      args=(arriving_thread_killer,
                                            arriving_messages_queue,
                                            arriving_messages_queue_threading_lock))
    arriving_messages_thread.start()
    logger.info("Started the thread the thread to read incoming messages that describe tasks.")
    #endregion



    #region received_messages_processing_thread
    logger.info("Starting the thread actually processing tasks.")
    received_messages_processing_thread = Thread(target=received_messages_processor,
                                                 args=(arriving_thread_killer,
                                                       arriving_messages_queue,
                                                       reporting_messages_queue,
                                                       s3))
    received_messages_processing_thread.start()
    logger.info("Started the thread actually processing tasks.")
    #endregion


    # region reporting_messages_thread
    logger.info("Starting the thread sending the reports to the bot.")
    reporting_thread = Thread(target=reporting_messaging_thread,
                                        args=(departing_thread_killer,
                                              reporting_messages_queue,
                                              reporting_messages_queue_threading_lock))
    reporting_thread.start()
    logger.info("Thread sending the reports started.")
    # endregion


    logger.info("Service started.")

    while True:
        try:
            pass
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Exiting.")
            departing_thread_killer.set_tokill(True)
            arriving_thread_killer.set_tokill(True)

            logger.info("Waiting for threads to finish.")
            # reporting_messaging_thread.join()
            received_messages_processing_thread.join()
            arriving_messages_thread.join()
            logger.info("Threads finished. Exiting.")

            break
        except Exception as e:
            logger.error("An error occurred.")
            logger.error(e)
            logger.error(traceback.format_exc())
            break

    logger.info("Finishing service.")

    
    
if __name__ == "__main__":
    main()