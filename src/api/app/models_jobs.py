from pydantic import BaseModel,Field
from typing import Dict, Any
import uuid 
from datetime import datetime,timezone
class JobCreateRequest(BaseModel):
    file_name: str = Field(..., min_length=3)
    contentType: str = Field(default="application/octet-stream")
    
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def job_to_entity(req:JobCreateRequest) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    ts = now_iso()
    return {
        "id": job_id,
        "pk": "JOB",
        "created_at": ts,
        "updated_at": ts,
        "file_name": req.file_name,
        "content_type": req.contentType,
        "status": "CREATED",
        "category": ""
    }
    
class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    category: str