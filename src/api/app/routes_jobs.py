import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from azure.cosmos.exceptions import CosmosHttpResponseError
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from .models_jobs import JobCreateRequest, job_to_entity, JobCreateResponse
from .cosmos import get_cosmos_container
from .blob_service import generate_url_upload_sas

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", status_code=201)
def create_job(req: JobCreateRequest):
    container = get_cosmos_container()
    entity = job_to_entity(req)
    try:
        container.create_item(body=entity)
    except CosmosHttpResponseError as e:
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")

    blob_path= f"input/{entity['id']}/{req.fileName}"
    upload_url = generate_url_upload_sas(blob_path)

    return JobCreateResponse(job_id=entity["id"], status=entity["status"], created_at=entity["created_at"], category=entity["category"],upload_url=upload_url)

@router.get("", status_code=200)
def get_jobs():
    return {"message": "ok"}

@router.get("/{job_id}", status_code=200)
def get_job(job_id: str):
    container = get_cosmos_container()
    try:
        item = container.read_item(item=job_id, partition_key="JOB")
        return item
    except CosmosHttpResponseError as e:
        if getattr(e, 'status_code', None) == 404:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")


@router.post("/{job_id}/retry", status_code=200)
def retry_job(job_id: str):
    container = get_cosmos_container()

    try:
        item = container.read_item(item=job_id, partition_key="JOB")
    except CosmosHttpResponseError as e:
        if getattr(e, 'status_code', None) == 404:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")

    if item.get("status") != "ERROR":
        raise HTTPException(status_code=400, detail="Le document n'est pas en erreur")

    correlation_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()
    file_name = item.get("fileName", "")

    message_body = {
        "documentId": job_id,
        "fileName": file_name,
        "blobName": f"input/{job_id}/{file_name}",
        "size": 0,
        "uploadedAt": uploaded_at,
        "correlationId": correlation_id,
    }

    conn_str = os.environ["SERVICE_BUS_CONNECTION_STRING"]
    queue_name = os.environ["SERVICE_BUS_QUEUE_NAME"]
    try:
        with ServiceBusClient.from_connection_string(conn_str) as client:
            with client.get_queue_sender(queue_name) as sender:
                sender.send_messages(ServiceBusMessage(json.dumps(message_body)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service Bus error: {e}")

    try:
        item["status"] = "QUEUED"
        item["updated_at"] = uploaded_at
        container.replace_item(item=job_id, body=item)
    except CosmosHttpResponseError as e:
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")

    return {"message": "Document remis en queue", "documentId": job_id}
