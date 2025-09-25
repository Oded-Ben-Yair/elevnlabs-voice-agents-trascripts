import requests
import os
from dotenv import load_dotenv

load_dotenv("../.env")

# Get token first
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
    print("✅ Got token")
    
    # Try to add user to dataset
    dataset_id = os.getenv('POWERBI_DATASET_ID')
    workspace_id = os.getenv('POWERBI_WORKSPACE_ID')
    
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/users"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    body = {
        "identifier": "39e95282-848b-4d78-ba1a-f6a9c7dc1fc9",
        "principalType": "App",
        "datasetUserAccessRight": "Read"
    }
    
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in [200, 201]:
        print("✅ Access granted successfully!")
    else:
        print(f"❌ Failed: {resp.status_code}")
        print(resp.text)
else:
    print(f"❌ Failed to get token: {response.status_code}")
