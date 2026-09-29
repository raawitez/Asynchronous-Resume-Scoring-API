import os
import json
import time
import signal
import pika
import tempfile
from loguru import logger
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from app.core.logger import setup_logger
from app.database import SessionLocal, engine, Base
from app.models.resume_model import Resume
from app.cache.redis_client import set_cache
from app.messaging.events import QUEUE_RESUME_PROCESSING
from app.core.s3_client import USE_S3, download_file_from_s3

from processing.parser import extract_text_from_pdf, PDFParseError
from processing.scorer import score_resume

setup_logger()

def get_db() -> Session:
    return SessionLocal()

def update_resume_status(
    resume_id: int,
    status: str,
    score: float = None,
    score_details: str = None
):
    db = get_db()
    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()

        if not resume:
            logger.error(f"[WORKER] Resume {resume_id} not found in DB")
            return

        resume.status = status

        if score is not None:
            resume.score = score
        if score_details is not None:
            resume.score_details = score_details

        db.commit()
        logger.info(f"[WORKER] Resume {resume_id} -> status='{status}'")

    except Exception as e:
        logger.error(f"[WORKER] DB update failed: {e}")
        db.rollback()
    finally:
        db.close()

def cache_score(resume_id: int, score_data: dict):
    cache_key = f"resume_score:{resume_id}"
    set_cache(cache_key, score_data, ttl=3600)
    logger.info(f"[WORKER] Score cached for resume {resume_id}")

def get_local_file_for_processing(file_path: str) -> str:
    """Download from S3 to tempfile if S3 is active; otherwise return local path."""
    if USE_S3:
        content = download_file_from_s3(file_path)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(content)
        tmp.close()
        return tmp.name
    return file_path

def process_resume(event: dict) -> bool:
    resume_id = event.get("resume_id")
    file_path = event.get("file_path")
    user_id = event.get("user_id")

    logger.info(f"\n{'-' * 60}")
    logger.info(f"[WORKER] Processing resume {resume_id}")
    logger.info(f"[WORKER] File: {file_path} | User: {user_id}")

    update_resume_status(resume_id, "processing")

    local_path = None
    
    try:
        logger.info(f"[WORKER] Fetching file for processing...")
        local_path = get_local_file_for_processing(file_path)

        logger.info(f"[WORKER] Extracting text from PDF...")
        text = extract_text_from_pdf(local_path)
        logger.info(f"[WORKER] Text extraction complete")

    except PDFParseError as e:
        logger.error(f"[WORKER] PDF parse failed: {e}")
        update_resume_status(resume_id, "failed")
        return False

    except Exception as e:
        logger.error(f"[WORKER] Unexpected parse error: {e}")
        update_resume_status(resume_id, "failed")
        return False
    finally:
        if USE_S3 and local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                logger.warning(f"[WORKER] Could not remove temp file {local_path}: {e}")

    logger.info(f"[WORKER] Scoring resume...")

    try:
        score_result = score_resume(text)
        total_score = score_result["total_score"]
        grade = score_result["grade"]
        logger.info(f"[WORKER] Score: {total_score}/100 Grade: {grade}")

    except Exception as e:
        logger.error(f"[WORKER] Scoring failed: {e}")
        update_resume_status(resume_id, "failed")
        return False

    logger.info(f"[WORKER] Saving score to database...")

    score_details_json = json.dumps({
        "breakdown": score_result["breakdown"],
        "keywords_found": score_result["keywords_found"],
        "feedback": score_result["feedback"],
        "grade": grade
    })

    update_resume_status(
        resume_id=resume_id,
        status="scored",
        score=total_score,
        score_details=score_details_json
    )

    cache_data = {
        "resume_id": resume_id,
        "status": "scored",
        "score": total_score,
        "score_details": {
            "breakdown": score_result["breakdown"],
            "keywords_found": score_result["keywords_found"],
            "feedback": score_result["feedback"],
            "grade": score_result["grade"]
        },
        "message": f"Score: {total_score}/100 (Grade: {grade})"
    }

    cache_score(resume_id, cache_data)
    logger.info(f"[WORKER] Resume {resume_id} processed successfully")
    return True

def on_message(ch, method, properties, body):
    logger.info("[WORKER] Message received from queue")
    try:
        event = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.error(f"[WORKER] Invalid JSON: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    success = process_resume(event)
    
    if success:
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("[WORKER] Message acknowledged")
    else:
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        logger.warning("[WORKER] Message rejected (not requeued)")

def main():
    Base.metadata.create_all(bind=engine)

    logger.info("=" * 60)
    logger.info("Asynchronous Resume Scoring Worker - Starting")
    logger.info("=" * 60)
    
    rabbitmq_url = os.getenv("RABBITMQ_URL")

    if rabbitmq_url:
        params = pika.URLParameters(rabbitmq_url)
        params.socket_timeout = 10.0
    else:
        params = pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            heartbeat=600,
            socket_timeout=10.0
        )

    logger.info("Connecting to RabbitMQ...")
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    logger.info("Connected to RabbitMQ")

    channel.queue_declare(queue=QUEUE_RESUME_PROCESSING, durable=True)
    logger.info(f"Queue '{QUEUE_RESUME_PROCESSING}' ready")

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=QUEUE_RESUME_PROCESSING,
        on_message_callback=on_message,
        auto_ack=False
    )

    logger.info("Listening for resume processing jobs...")
    logger.info("=" * 60)

    def shutdown(sig, frame):
        logger.info("Shutting down worker...")
        channel.stop_consuming()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        channel.start_consuming()
    finally:
        if connection and not connection.is_closed:
            connection.close()
        logger.info("Worker stopped.")

if __name__ == "__main__":
    main()