from flask import Flask, request, render_template
import openai
import os
import boto3
import json
from openai import OpenAI
import logging

def get_secret(secret_name, region_name="us-east-1"):
    """
    Fetches a secret from AWS Secrets Manager.
    """
    # Create a Secrets Manager client
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_name)
        # Secrets Manager returns a string, parse if necessary
        secret = response.get("SecretString")
        return json.loads(secret) if secret else None
    except Exception as e:
        raise Exception(f"Error retrieving secret: {e}")

# Replace 'your-secret-name' with the name of your secret in Secrets Manager
secret_name = "openai_api_key"
region_name = "us-east-1"  # Adjust the region if necessary

# Get the secret
secret = get_secret(secret_name, region_name)

# Extract the OpenAI API key from the secret
openai_api_key = secret['api_key']

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
