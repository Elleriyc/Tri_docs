import azure.functions as func
import logging
import os
import json
import uuid
from datetime import datetime, timezone
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError
from azure.servicebus import ServiceBusClient, ServiceBusMessage

app = func.FunctionApp()

STOPWORDS = {"le","la","les","de","du","des","un","une","et","ou","en","au","aux","par","pour","sur","dans","avec"}


def get_cosmos_container():
    client = CosmosClient(
        url=os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"]
    )
    db = client.get_database_client(os.environ["COSMOS_DATABASE"])
    return db.get_container_client(os.environ["COSMOS_CONTAINER"])


def send_signalr_notification(payload: dict) -> None:
    import urllib.request
    import urllib.error
    import urllib.parse
    import hmac
    import hashlib
    import base64
    import time

    conn_str = os.environ["SIGNALR_CONNECTION_STRING"]
    params = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    endpoint = params.get("Endpoint", "").rstrip("/")
    access_key = params.get("AccessKey", "")

    hub = "notifications"
    url = f"{endpoint}/api/v1/hubs/{hub}"

    expiry = int(time.time()) + 300
    string_to_sign = f"{url}\n{expiry}"
    try:
        key_bytes = base64.b64decode(access_key)
    except Exception:
        key_bytes = access_key.encode()

    signature = base64.b64encode(
        hmac.new(key_bytes, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode()
    token = (
        f"Audience={urllib.parse.quote(url, safe='')}"
        f"&Expires={expiry}"
        f"&Signature={urllib.parse.quote(signature, safe='')}"
    )

    body = json.dumps({"target": "documentUpdate", "arguments": [payload]}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            logging.info(json.dumps({
                "step": "SIGNALR_NOTIFY",
                "status": "SUCCESS",
                "message": f"SignalR HTTP {resp.status}",
                "documentId": payload.get("documentId"),
            }))
    except urllib.error.HTTPError as e:
        logging.warning(json.dumps({
            "step": "SIGNALR_NOTIFY",
            "status": "ERROR",
            "message": f"SignalR HTTP error {e.code}: {e.reason}",
            "documentId": payload.get("documentId"),
        }))


def publish_to_service_bus(message_body: dict) -> None:
    conn_str = os.environ["SERVICE_BUS_CONNECTION_STRING"]
    queue_name = os.environ["SERVICE_BUS_QUEUE_NAME"]
    with ServiceBusClient.from_connection_string(conn_str) as client:
        with client.get_queue_sender(queue_name) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(message_body)))


def generate_tags(file_name: str) -> list:
    import re
    # Extract extension before cleaning
    ext = ""
    if "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower()

    # Clean: replace _, -, . with spaces; lowercase; remove extension
    cleaned = re.sub(r"[_\-.]", " ", file_name).lower()
    # Remove extension portion at end
    if ext:
        cleaned = re.sub(rf"\s*{re.escape(ext)}\s*$", "", cleaned)

    words = cleaned.split()
    tags = [w for w in words if len(w) >= 2 and w not in STOPWORDS]

    # Contextual tags
    if any(w in ("cv", "resume") for w in tags):
        tags.append("rh")
    if any(w in ("facture", "invoice") for w in tags):
        tags.append("comptabilite")
    if any(w in ("contrat", "contract") for w in tags):
        tags.append("juridique")
    if any(w in ("rapport", "report") for w in tags):
        tags.append("rapport")

    if ext:
        tags.append(ext)

    # Deduplicate preserving order, keep 3-8 tags
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:8] if len(unique) >= 3 else unique


# ---------------------------------------------------------------------------
# 1. Blob Trigger — extended
# ---------------------------------------------------------------------------

@app.blob_trigger(arg_name="myblob", path="docs",
                  connection="tristockage_STORAGE")
def WorkerUpload(myblob: func.InputStream):
    correlation_id = str(uuid.uuid4())

    logging.info(json.dumps({
        "correlationId": correlation_id,
        "step": "BLOB_TRIGGER",
        "status": "START",
        "message": f"Blob received: {myblob.name} ({myblob.length} bytes)",
    }))

    if not myblob.name:
        logging.warning("Blob name is None, skipping")
        return

    parts = myblob.name.split("/")
    if len(parts) < 3 or parts[0] != "input":
        logging.warning(f"Unexpected blob path format: {myblob.name}")
        return

    job_id = parts[1]
    file_name = parts[2]
    uploaded_at = datetime.now(timezone.utc).isoformat()

    # --- Update CosmosDB: UPLOADED ---
    try:
        container = get_cosmos_container()
        item = container.read_item(item=job_id, partition_key="JOB")
        item["status"] = "UPLOADED"
        item["updated_at"] = uploaded_at
        container.replace_item(item=job_id, body=item)
        logging.info(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "SUCCESS",
            "message": "Status set to UPLOADED in CosmosDB",
        }))
    except CosmosHttpResponseError as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "ERROR",
            "message": f"CosmosDB error: {e}",
        }))
        return

    # --- SignalR: UPLOADED ---
    try:
        send_signalr_notification({
            "documentId": job_id,
            "status": "UPLOADED",
            "message": "Fichier reçu",
        })
    except Exception as e:
        logging.warning(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "ERROR",
            "message": f"SignalR notification failed: {e}",
        }))

    # --- Publish to Service Bus ---
    message_body = {
        "documentId": job_id,
        "fileName": file_name,
        "blobName": myblob.name,
        "size": myblob.length,
        "uploadedAt": uploaded_at,
        "correlationId": correlation_id,
    }
    try:
        publish_to_service_bus(message_body)
        logging.info(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "SUCCESS",
            "message": "Message published to Service Bus",
        }))
    except Exception as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "ERROR",
            "message": f"Service Bus publish failed: {e}",
        }))
        return

    # --- Update CosmosDB: QUEUED ---
    try:
        container = get_cosmos_container()
        item = container.read_item(item=job_id, partition_key="JOB")
        item["status"] = "QUEUED"
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        container.replace_item(item=job_id, body=item)
        logging.info(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "SUCCESS",
            "message": "Status set to QUEUED in CosmosDB",
        }))
    except CosmosHttpResponseError as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": job_id,
            "step": "BLOB_TRIGGER",
            "status": "ERROR",
            "message": f"CosmosDB QUEUED update error: {e}",
        }))


# ---------------------------------------------------------------------------
# 2. Service Bus Processor
# ---------------------------------------------------------------------------

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-processing",
    connection="SERVICE_BUS_CONNECTION_STRING",
)
def ProcessDocument(msg: func.ServiceBusMessage):
    raw = msg.get_body().decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error(json.dumps({
            "step": "PROCESS_DOCUMENT",
            "status": "ERROR",
            "message": f"Invalid JSON in message: {e}",
        }))
        raise

    document_id = payload.get("documentId", "")
    file_name = payload.get("fileName", "")
    correlation_id = payload.get("correlationId", str(uuid.uuid4()))

    logging.info(json.dumps({
        "correlationId": correlation_id,
        "documentId": document_id,
        "step": "PROCESS_DOCUMENT",
        "status": "START",
        "message": "Service Bus message received",
    }))

    # --- Update CosmosDB: PROCESSING ---
    try:
        container = get_cosmos_container()
        item = container.read_item(item=document_id, partition_key="JOB")
        item["status"] = "PROCESSING"
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        container.replace_item(item=document_id, body=item)
    except CosmosHttpResponseError as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "PROCESS_DOCUMENT",
            "status": "ERROR",
            "message": f"CosmosDB PROCESSING update error: {e}",
        }))
        raise

    # --- SignalR: PROCESSING ---
    try:
        send_signalr_notification({
            "documentId": document_id,
            "status": "PROCESSING",
            "message": "Traitement IA en cours",
        })
    except Exception as e:
        logging.warning(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "PROCESS_DOCUMENT",
            "status": "ERROR",
            "message": f"SignalR PROCESSING notification failed: {e}",
        }))

    # --- AI Tagging ---
    logging.info(json.dumps({
        "correlationId": correlation_id,
        "documentId": document_id,
        "step": "AI_TAGGING",
        "status": "START",
        "message": f"Generating tags for: {file_name}",
    }))
    tags = generate_tags(file_name)
    logging.info(json.dumps({
        "correlationId": correlation_id,
        "documentId": document_id,
        "step": "AI_TAGGING",
        "status": "SUCCESS",
        "message": f"Tags generated: {tags}",
    }))

    # --- Update CosmosDB: PROCESSED ---
    processed_at = datetime.now(timezone.utc).isoformat()
    try:
        container = get_cosmos_container()
        item = container.read_item(item=document_id, partition_key="JOB")
        item["status"] = "PROCESSED"
        item["tags"] = tags
        item["processedAt"] = processed_at
        item["updated_at"] = processed_at
        container.replace_item(item=document_id, body=item)
        logging.info(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "PROCESS_DOCUMENT",
            "status": "SUCCESS",
            "message": "Status set to PROCESSED in CosmosDB",
        }))
    except CosmosHttpResponseError as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "PROCESS_DOCUMENT",
            "status": "ERROR",
            "message": f"CosmosDB PROCESSED update error: {e}",
        }))
        raise

    # --- SignalR: PROCESSED ---
    try:
        send_signalr_notification({
            "documentId": document_id,
            "status": "PROCESSED",
            "message": "Tagging terminé",
            "tags": tags,
        })
    except Exception as e:
        logging.warning(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "PROCESS_DOCUMENT",
            "status": "ERROR",
            "message": f"SignalR PROCESSED notification failed: {e}",
        }))


# ---------------------------------------------------------------------------
# 3. DLQ Alert
# ---------------------------------------------------------------------------

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-processing/$deadletterqueue",
    connection="SERVICE_BUS_CONNECTION_STRING",
)
def ProcessDLQ(msg: func.ServiceBusMessage):
    raw = msg.get_body().decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logging.error(json.dumps({
            "step": "DLQ_ALERT",
            "status": "ERROR",
            "message": "DLQ message is not valid JSON, skipping",
        }))
        return

    document_id = payload.get("documentId")
    correlation_id = payload.get("correlationId", str(uuid.uuid4()))

    if not document_id:
        logging.warning(json.dumps({
            "correlationId": correlation_id,
            "step": "DLQ_ALERT",
            "status": "ERROR",
            "message": "DLQ message missing documentId, skipping",
        }))
        return

    logging.info(json.dumps({
        "correlationId": correlation_id,
        "documentId": document_id,
        "step": "DLQ_ALERT",
        "status": "START",
        "message": "DLQ message received",
    }))

    error_at = datetime.now(timezone.utc).isoformat()

    # --- Update CosmosDB: ERROR ---
    try:
        container = get_cosmos_container()
        item = container.read_item(item=document_id, partition_key="JOB")
        item["status"] = "ERROR"
        item["errorMessage"] = "Processing failed after maximum retries"
        item["errorAt"] = error_at
        item["updated_at"] = error_at
        container.replace_item(item=document_id, body=item)
        logging.info(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "DLQ_ALERT",
            "status": "SUCCESS",
            "message": "Status set to ERROR in CosmosDB",
        }))
    except CosmosHttpResponseError as e:
        logging.error(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "DLQ_ALERT",
            "status": "ERROR",
            "message": f"CosmosDB ERROR update failed: {e}",
        }))

    # --- SignalR: ERROR ---
    try:
        send_signalr_notification({
            "documentId": document_id,
            "status": "ERROR",
            "message": "Erreur de traitement",
        })
    except Exception as e:
        logging.warning(json.dumps({
            "correlationId": correlation_id,
            "documentId": document_id,
            "step": "DLQ_ALERT",
            "status": "ERROR",
            "message": f"SignalR ERROR notification failed: {e}",
        }))


# ---------------------------------------------------------------------------
# 4. SignalR Negotiate
# ---------------------------------------------------------------------------

@app.route(route="negotiate", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET", "POST"])
def negotiate(req: func.HttpRequest) -> func.HttpResponse:
    import hmac
    import hashlib
    import base64
    import time
    import json

    conn_str = os.environ["SIGNALR_CONNECTION_STRING"]
    params = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    endpoint = params.get("Endpoint", "").rstrip("/")
    access_key = params.get("AccessKey", "")

    hub = "notifications"
    hub_url = f"{endpoint}/client/?hub={hub}"
    expiry = int(time.time()) + 3600

    try:
        key_bytes = base64.b64decode(access_key + "==")
    except Exception:
        key_bytes = access_key.encode()

    # Build JWT
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()

    payload = base64.urlsafe_b64encode(
        json.dumps({
            "aud": hub_url,
            "exp": expiry,
            "iat": int(time.time()),
        }).encode()
    ).rstrip(b"=").decode()

    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(
            key_bytes,
            signing_input.encode("utf-8"),
            hashlib.sha256
        ).digest()
    ).rstrip(b"=").decode()

    jwt_token = f"{signing_input}.{signature}"

    result = {
        "url": hub_url,
        "accessToken": jwt_token,
    }

    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )
