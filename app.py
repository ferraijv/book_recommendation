from flask import Flask, request, render_template
import openai
import os
import boto3
import json
from openai import OpenAI
import logging

def get_secrets():
    """Retrieves secrets based on the environment."""
    try:
        if "RENDER" in os.environ:  # Check if running on Render
            logging.info("Running on Render, using secret files")
            secrets_path = "/etc/secrets/openai.json"
            try:
                with open(secrets_path, "r") as f:
                    secrets = json.load(f)
                    return secrets
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logging.error(f"Error reading Render secrets: {e}")
                return None
        else:  # Running locally
            logging.info("Running locally, using AWS Secrets Manager")
            secret_name = "openai_api_key"  # Replace with your secret name
            region_name = os.environ.get("AWS_REGION", "us-east-1") # get region from env if available otherwise default
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

# Example usage (in your main app code):
secrets = get_secrets()

# Extract the OpenAI API key from the secret
openai_api_key = secrets['api_key']

client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=openai_api_key,
)

# Initialize Flask app
app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    recommendations = None
    if request.method == "POST":
        user_input = request.form.get("preferences")
        if user_input:
            try:
                # Call ChatGPT for book recommendations
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant providing book recommendations."},
                        {"role": "user", "content": f"Recommend books based on these preferences: {user_input}"}
                    ]
                )
                logging.info(response)
                recommendations = response.choices[0].message.content.strip()
            except Exception as e:
                recommendations = f"Error: {e}"

    return render_template("index.html", recommendations=recommendations)

if __name__ == "__main__":
    app.run(debug=True)
