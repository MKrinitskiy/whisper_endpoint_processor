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
from regex import F
from thread_killer import ThreadKiller
from async_rabbitmq_consumer import ReconnectingRabbitMQConsumer
from async_rabbitmq_publisher import RabbitMQPublisher
from service_defs import EnsureDirectoryExists, DoesPathExistAndIsFile, DoesPathExistAndIsDirectory

import config
import tempfile
import base64
from minio import Minio
from minio.error import S3Error



def received_messages_processor(tokill: ThreadKiller,
                                arriving_messages_queue: Queue,
                                reporting_messages_queue: Queue,
                                s3: Minio):
    """Threaded worker for processing the received messages from RabbitMQ.
    tokill is a thread_killer object that indicates whether a thread should be terminated
    arriving_messages_queue is a limited size thread-safe Queue instance that contains the received messages.
    """
    logger = logging.getLogger("received_messages_processor")
    logger.info("Threaded received_messages_processor started")

    def process_file(file_path):
        # TODO: Pass the file to the model for processing
        logger.info(f"File to process exists: {DoesPathExistAndIsFile(file_path)}")
        if not DoesPathExistAndIsFile(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False
        logger.info(f"Starting to process the file: {file_path}")

        # mock TXT file creation
        txt_fn = f'/tmp/{os.path.basename(file_path)}.txt'
        txt_tempfile = tempfile.NamedTemporaryFile(delete=False)
        os.rename(txt_tempfile.name, txt_fn)
        with open(txt_fn, 'w') as f:
            f.write("This is a mock text file.")
        logger.info(f"TXT file created: {txt_fn}")

        # mock SRT file creation
        srt_fn = f'/tmp/{os.path.basename(file_path)}.srt'
        srt_tempfile = tempfile.NamedTemporaryFile(delete=False)
        os.rename(srt_tempfile.name, srt_fn)
        with open(srt_fn, 'w') as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nThis is a mock SRT file.")
        logger.info(f"SRT file created: {srt_fn}")


        # TODO: Save the results in Minio as TXT and SRT files
        logger.info(f"The file {file_path} has been processed.")
        # TODO: Report the task being done to RabbitMQ (reporting_messages_queue)
        return txt_fn, srt_fn
    
    

    def download_and_process_file_from_minio(file_path, bucket_name):
        logger.info(f"Starting to download and process file {file_path}")
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            # Download the file from Minio
            #                       "filename": "MK-voice-example-002.mp3",
            #                       "bucket": "whisper-telegram-bot",
            #                       "file_path": "190f416f78ca4539878e7f1a7008f5b9.mp3",
            logger.info(f"Downloading file from Minio: {file_path}")
            s3.fget_object(bucket_name, file_path, temp_file.name)
            tempfile_name = temp_file.name
            logger.info(f"File downloaded from Minio: {temp_file.name}")
            logger.info(f"Renaming {temp_file.name} to /tmp/{file_path}")
            os.rename(temp_file.name, f'/tmp/{file_path}')

            # Process the downloaded file
            txt_fn, srt_fn = process_file(f'/tmp/{file_path}')

            logger.info(f"Renaming back /tmp/{file_path} to {temp_file.name}")
            os.rename(f'/tmp/{file_path}', temp_file.name)
            
            logger.info(f"Finished processing file {file_path}")
            logger.info(f"tempfile {tempfile_name} exists: {DoesPathExistAndIsFile(tempfile_name)}")
            logger.info(f"tempfile /tmp/{file_path} exists: {DoesPathExistAndIsFile(f'/tmp/{file_path}')}")
            return {'result': True, 'txt_fn': txt_fn, 'srt_fn': srt_fn}
        except S3Error as e:
            logger.error(f"Failed downloading file from Minio: {e}")
            return {'result': False, 'txt_fn': None, 'srt_fn': None}
        except Exception as e:
            logger.error(f"An error occurred while downloading the file from Minio: {e}")
            return {'result': False, 'txt_fn': None, 'srt_fn': None}
    


    def send_results_to_minio(txt_fn: str, srt_fn: str):
        try:
            # Generate a unique filename for the file in Minio
            unique_filename = str(uuid.uuid4())

            # Upload the TXT file to Minio
            s3.fput_object(bucket_name, unique_filename + '.txt', txt_fn)
            logger.info(f"TXT file uploaded to Minio: {unique_filename}.txt")

            # Upload the SRT file to Minio
            s3.fput_object(bucket_name, unique_filename + '.srt', srt_fn)
            logger.info(f"SRT file uploaded to Minio: {unique_filename}.srt")

            logger.info(f"Files {txt_fn} and {srt_fn} uploaded to Minio successfully.")

            return {"result": True,
                    "txt_fn": unique_filename + '.txt',
                    "srt_fn": unique_filename + '.srt'}
        except Exception as e:
            logger.error(f"An error occurred while uploading files to Minio: {e}")
            return {"result": False, "txt_fn": None, "srt_fn": None}


    while not tokill():
        try:
            message = arriving_messages_queue.get(block=True, timeout=1)
            message = json.loads(message.decode("utf-8"))
            logger.info(f"Received message: {message}")
            logger.info(f"Processing the message...")

            #region Received message example
            # Received message:  '{'user_id': 600906,
            #                      'task_id': '29aa85af-a830-4346-b6e0-2d19f40cfab1',
            #                      'filename': 'MK-voice-example-003.mp3',
            #                      'minio_bucket': 'whisper-telegram-bot',
            #                      'file_path': '3d1f882767864f269470ea9558022892.mp3',
            #                      'transcription_lang': 'ru',
            #                      'queue_name': 'task_queue',
            #                      'status': 'queued',
            #                      'start_time': '2024-08-18T00:44:48'}'
            #endregion
            
            # Extract the file path from the message


            file_path = message["file_path"]
            logger.info(f"File path to get and process: {file_path}")
            bucket_name = message["minio_bucket"]
            logger.info(f"Bucket name to get the file from: {bucket_name}")

            # Download and process the file
            download_and_processing_result = download_and_process_file_from_minio(file_path, bucket_name)

            if download_and_processing_result['result']:
                logger.info(f"File downloaded and processed successfully.")
                logger.info(f"Sending the results to the minio storage.")

                # Send the results to Minio
                results_sent = send_results_to_minio(download_and_processing_result['txt_fn'], download_and_processing_result['srt_fn'])
                # {"result": True,
                #  "txt_fn": unique_filename + '.txt',
                #  "srt_fn": unique_filename + '.srt'}


                if results_sent['result']:
                    logger.info(f"Results sent to minio successfully.")
                    logger.info(f"Reporting the task being done to RabbitMQ.")

                    # Report the task being done to RabbitMQ
                    reporting_message = {
                        "user_id": message["user_id"],
                        "task_id": message["task_id"],
                        "txt_fn": results_sent['txt_fn'],
                        "srt_fn": results_sent['srt_fn'],
                        "processing_result": "success"
                    }
                    reporting_messages_queue.put(reporting_message, block=True)


                else:
                    logger.error(f"Failed to send the results to minio.")
                    continue
            else:
                logger.error(f"Failed to download or process the file.")
                continue

            # TODO: download the file from minio - DONE
            # TODO: pass the file to the model
            # We need to decide whether the model should be run here or in another container.
            # TODO: save the results in minio as TXT and SRT files - DONE
            # TODO: report the task being done to rabbitmq (reporting_messages_queue) - DONE
            # The bot will then send the user the results.
            # TODO: send the reporting message to task manager bot via RabbitMQ

        except Empty:
            continue

    logger.info("received_messages_processing exiting")
