import os 
import boto3
from botocore.exceptions import ClientError
from loguru import logger

USE_S3 = os.getenv("USE_S3", "false").lower() == "true"

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

_s3_client = None

if USE_S3:
    _s3_client = boto3.client("s3", region_name = AWS_REGION)

def upload_file_to_s3(file_bytes: bytes, key: str) -> str:
    try:
        _s3_client.put_object(
            Bucket = S3_BUCKET_NAME,
            Key = key,
            Body = file_bytes,
            ContentType = "application/pdf"
        )
        logger.info(f"[S3] Uploaded {key} to bucket {S3_BUCKET_NAME}")
        return key

    except ClientError as e:
        logger.error(f"[S3] Upload failed for {key}: {e}")
        raise

def download_file_from_s3(key: str) -> bytes:
    try:
        response = _s3_client.get_object(Bucket=S3_BUCKET_NAME, Key = key)
        return response["Body"].read()
    except ClientError as e:
        logger.error(f"[S3] Download failed for {key}: {e}")
        raise