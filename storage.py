import os

import boto3
from botocore.config import Config

bucket = os.environ["R2_BUCKET"]

client = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

def image_url(key):
    if not key:
        return None

    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=900,
    )

def put_image(key, body):
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="image/jpeg"
    )

def delete_images(keys):
    if not keys:
        return

    result = client.delete_objects(
        Bucket=bucket,
        Delete={"Objects": [{"Key": key} for key in keys]},
    )

    if result.get("Errors"):
        raise RuntimeError("R2 could not delete all requested images")

def read_image(key):
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        return body.read()
    finally:
        body.close()