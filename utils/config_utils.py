import os
import json
import boto3
import logging

def get_secrets(secret_name) -> dict:
    """Retrieves secrets based on the environment."""
    try:
        if "RENDER" in os.environ:  # Check if running on Render
            logging.info("Running on Render, using secret files")
            secrets_path = f"/etc/secrets/{secret_name}.json"
            try:
                with open(secrets_path, "r") as f:
                    secrets = json.load(f)
                    return secrets
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logging.error(f"Error reading Render secrets: {e}")
                return None
        else:  # Running locally
            logging.info("Running locally, using AWS Secrets Manager")
            region_name = os.environ.get("AWS_REGION",
                                         "us-east-1")  # get region from env if available otherwise default
            try:
                session = boto3.session.Session()
                client = session.client(
                    service_name='secretsmanager',
                    region_name=region_name
                )
                get_secret_value_response = client.get_secret_value(SecretId=secret_name)
                secret = get_secret_value_response['SecretString']
                return json.loads(secret)
            except Exception as e:
                logging.error(f"Error retrieving AWS secret: {e}")
                return None
    except Exception as e:
        logging.exception("A top level exception occurred")
        return None