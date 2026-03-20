from fastapi import APIRouter, HTTPException
from .models_jobs import JobCreateRequest, job_to_entity, JobCreateResponse
from .cosmos import get_cosmos_container
from azure.cosmos.exceptions import CosmosHttpResponseError


router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", status_code=201)
def create_job(req: JobCreateRequest):
    container = get_cosmos_container()
    entity = job_to_entity(req)
    try:
        container.create_item(body=entity)
    except CosmosHttpResponseError as e:
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")
    return JobCreateResponse(job_id=entity["id"], status=entity["status"], created_at=entity["created_at"], category=entity["category"])

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