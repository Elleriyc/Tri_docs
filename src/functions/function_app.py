import azure.functions as func
import logging
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError

app = func.FunctionApp()

def get_cosmos_container():
    client = CosmosClient(
        url=os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"]
    )
    db = client.get_database_client(os.environ["COSMOS_DATABASE"])
    return db.get_container_client(os.environ["COSMOS_CONTAINER"])

@app.blob_trigger(arg_name="myblob", path="docs",
                               connection="tristockage_STORAGE")
def WorkerUpload(myblob: func.InputStream):
    logging.info(f"Python blob trigger function processed blob"
                f"Name: {myblob.name}"
                f"Blob Size: {myblob.length} bytes")

    # Blob path format: input/{job_id}/{fileName}
    if not myblob.name:
        logging.warning("Blob name is None, skipping")
        return

    parts = myblob.name.split("/")
    if len(parts) < 3 or parts[0] != "input":
        logging.warning(f"Unexpected blob path format: {myblob.name}")
        return

    job_id = parts[1]

    try:
        container = get_cosmos_container()
        item = container.read_item(item=job_id, partition_key="JOB")
        item["status"] = "UPLOADED"
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        container.replace_item(item=job_id, body=item)
        logging.info(f"Job {job_id} status updated to UPLOADED")
    except CosmosHttpResponseError as e:
        logging.error(f"CosmosDB error for job {job_id}: {e}")



# This example uses SDK types to directly access the underlying BlobClient object provided by the Blob storage trigger.
# To use, uncomment the section below and add azurefunctions-extensions-bindings-blob to your requirements.txt file
# Ref: aka.ms/functions-sdk-blob-python
#
# import azurefunctions.extensions.bindings.blob as blob
# @app.blob_trigger(arg_name="client", path="doc",
#                   connection="tristockage_STORAGE")
# def WorkerUpload(client: blob.BlobClient):
#     logging.info(
#         f"Python blob trigger function processed blob \n"
#         f"Properties: {client.get_blob_properties()}\n"
#         f"Blob content head: {client.download_blob().read(size=1)}"
#     )
