import os
import json
from datetime import datetime
from google.cloud import storage
from config import logger

def get_gcs_client():
    try:
        client = storage.Client()
        return client
    except Exception as e:
        logger.error(f"Error creating GCS client: {e}")
        return None

def upload_conversation(conversation_data):
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        logger.error("GCS_BUCKET_NAME environment variable not set.")
        return

    client = get_gcs_client()
    if not client:
        return

    try:
        bucket = client.get_bucket(bucket_name)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        user_email = conversation_data.get("user", "unknown-user")
        sanitized_email = user_email.replace("@", "_").replace(".", "_")
        filename = f"conversation-{timestamp}-{sanitized_email}.json"
        blob = bucket.blob(filename)
        blob.upload_from_string(
            json.dumps(conversation_data, indent=4),
            content_type="application/json"
        )
        logger.warning(f"Conversation uploaded to gs://{bucket_name}/{filename}")
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")

def download_conversation(file_uri):
    client = get_gcs_client()
    if not client:
        return None

    try:
        bucket_name, blob_name = file_uri.replace("gs://", "").split("/", 1)
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        conversation_content = blob.download_as_text()
        return json.loads(conversation_content)
    except Exception as e:
        logger.error(f"Error downloading from GCS: {e}")
        return None
