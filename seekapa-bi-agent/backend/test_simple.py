import requests
import os
from dotenv import load_dotenv

load_dotenv("../.env")

# Test with a very simple DAX query
simple_dax = "EVALUATE ROW(\"Test\", 1)"

# Get token
token_url = f"https://login.microsoftonline.com/{os.getenv('POWERBI_TENANT_ID')}/oauth2/v2.0/token"
data = {
    'client_id': os.getenv('POWERBI_CLIENT_ID'),
    'client_secret': os.getenv('POWERBI_CLIENT_SECRET'),
    'scope': os.getenv('POWERBI_SCOPE'),
    'grant_type': 'client_credentials'
}

response = requests.post(token_url, data=data)
if response.status_code == 200:
    token = response.json()['access_token']
    
    # Execute simple query
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{os.getenv('POWERBI_WORKSPACE_ID')}/datasets/{os.getenv('POWERBI_DATASET_ID')}/executeQueries"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    body = {
        "queries": [{"query": simple_dax}]
    }
    
    resp = requests.post(url, headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(resp.text)
