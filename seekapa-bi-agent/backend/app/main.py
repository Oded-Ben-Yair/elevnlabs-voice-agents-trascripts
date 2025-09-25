"""Seekapa BI Agent - Enhanced with Security Hardening and Streaming Datasets"""
import os
import base64
import logging
import secrets
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json

# Import enhanced services
from app.services.powerbi_service import PowerBIService
from app.api.powerbi import router as powerbi_router

# Import security middleware
from app.middleware import (
    OAuth2PKCEMiddleware,
    SecurityHeadersMiddleware,
    CSRFMiddleware,
    InputValidationMiddleware,
    AuditLoggingMiddleware,
    RateLimitMiddleware
)
from app.core.security import SecurityLevel, TokenManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv("../.env")

app = FastAPI(
    title="Seekapa BI Agent",
    description="Security-Hardened AI-Powered BI Agent with OAuth 2.1, Content Safety, and Power BI Integration",
    version="3.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    openapi_url="/openapi.json" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None
)

# Security Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
token_manager = TokenManager(SECRET_KEY)

# Add security middleware in correct order (order matters!)
# 1. Rate limiting (first to prevent DDoS)
app.add_middleware(RateLimitMiddleware)

# 2. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. Audit logging
app.add_middleware(AuditLoggingMiddleware)

# 4. Input validation
app.add_middleware(InputValidationMiddleware)

# 5. CSRF protection
app.add_middleware(CSRFMiddleware)

# 6. OAuth 2.1 with PKCE
app.add_middleware(OAuth2PKCEMiddleware, secret_key=SECRET_KEY)

# 7. Trusted host validation
allowed_hosts = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,app.seekapa.com").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# 8. CORS (more restrictive)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "https://app.seekapa.com,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    max_age=86400
)

# Include the enhanced PowerBI router
app.include_router(powerbi_router, prefix="/api/v1/powerbi", tags=["Power BI"])

# Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_AI_ENDPOINT = os.getenv("AZURE_AI_SERVICES_ENDPOINT")
GPT5_DEPLOYMENT = os.getenv("GPT5_DEPLOYMENT", "gpt-5")

# Initialize enhanced PowerBI service
powerbi_service = PowerBIService()
logger.info("Initialized enhanced PowerBI service with streaming support")

class QueryRequest(BaseModel):
    query: str
    model: Optional[str] = "gpt-5"

class QueryResponse(BaseModel):
    success: bool
    query: str
    response: str
    data: Optional[Dict] = None
    reports: Optional[List] = None
    embed_url: Optional[str] = None

async def get_workspace_reports():
    """Get all reports using enhanced service"""
    try:
        return await powerbi_service.get_workspace_reports()
    except Exception as e:
        logger.error(f"Error getting reports: {str(e)}")
        return []

async def get_report_pages(report_id: str):
    """Get pages of a specific report using standard API"""
    try:
        token = await powerbi_service.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}

        url = f"{powerbi_service.api_url}/groups/{powerbi_service.workspace_id}/reports/{report_id}/pages"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('value', [])
                else:
                    logger.error(f"Failed to get report pages: {resp.status}")
                    return []
    except Exception as e:
        logger.error(f"Error getting report pages: {str(e)}")
        return []

async def generate_embed_token(report_id: str, username: str = None, roles: List[str] = None):
    """Generate embed token with optional RLS using enhanced service"""
    try:
        if username and roles:
            return await powerbi_service.generate_embed_token_with_rls(report_id, username, roles)
        else:
            # Standard embed token without RLS
            token = await powerbi_service.get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{powerbi_service.api_url}/groups/{powerbi_service.workspace_id}/reports/{report_id}/GenerateToken"
            body = {"accessLevel": "View"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Failed to generate embed token: {resp.status}")
                        return None
    except Exception as e:
        logger.error(f"Error generating embed token: {str(e)}")
        return None

async def call_gpt5(prompt: str):
    """Call GPT-5 with proper parameters"""
    headers = {
        "api-key": AZURE_OPENAI_API_KEY,
        "Content-Type": "application/json"
    }
    
    url = f"{AZURE_AI_ENDPOINT}/openai/deployments/{GPT5_DEPLOYMENT}/chat/completions?api-version=2025-01-01-preview"
    
    body = {
        "messages": [
            {"role": "system", "content": "You are a business intelligence assistant that helps users understand their Power BI reports and data."},
            {"role": "user", "content": prompt}
        ],
        "max_completion_tokens": 1000
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['choices'][0]['message']['content']
            else:
                return "Unable to process request with AI at this time."

def map_query_to_report(query: str, reports: List[Dict]) -> Optional[Dict]:
    """Map natural language query to appropriate report"""
    query_lower = query.lower()
    
    # Keywords to report mapping
    keywords_map = {
        "sales": ["sales", "revenue", "income"],
        "customer": ["customer", "client", "user"],
        "product": ["product", "item", "inventory"],
        "performance": ["performance", "kpi", "metrics"],
        "analysis": ["analysis", "analytics", "insight"]
    }
    
    for report in reports:
        report_name = report.get('name', '').lower()
        for category, keywords in keywords_map.items():
            if any(kw in query_lower for kw in keywords):
                if category in report_name or any(kw in report_name for kw in keywords):
                    return report
    
    # Return first report if no match
    return reports[0] if reports else None

@app.get("/")
async def root():
    return {
        "message": "Seekapa BI Agent API",
        "version": "2.0.0",
        "status": "operational",
        "approach": "Using Reports API as per sys admin instructions"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/v1/query/", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Enhanced BI query processing with streaming support and improved error handling"""
    try:
        logger.info(f"Processing query: {request.query}")

        # Step 1: Get all reports using enhanced service
        reports = await get_workspace_reports()

        if not reports:
            logger.warning("No reports found in workspace")
            return QueryResponse(
                success=False,
                query=request.query,
                response="No reports found in the workspace. Please check permissions and ensure reports exist.",
                reports=[]
            )

        # Step 2: Map query to appropriate report
        selected_report = map_query_to_report(request.query, reports)

        if selected_report:
            report_id = selected_report['id']
            report_name = selected_report['name']
            logger.info(f"Selected report: {report_name}")

            # Step 3: Get report details
            pages = await get_report_pages(report_id)

            # Step 4: Generate embed token for visualization (with enhanced error handling)
            embed_token_data = await generate_embed_token(report_id)
            embed_url = selected_report.get('embedUrl', '')

            # Step 5: Check for streaming datasets related to this report
            try:
                streaming_datasets = await powerbi_service.get_streaming_datasets()
                has_streaming = len(streaming_datasets) > 0
            except Exception as e:
                logger.warning(f"Could not get streaming datasets: {str(e)}")
                has_streaming = False

            # Step 6: Generate enhanced AI response
            streaming_info = "\n\nThis workspace also has streaming datasets available for real-time analytics." if has_streaming else ""

            prompt = f"""
            User Query: {request.query}

            Found Report: {report_name}
            Report ID: {report_id}
            Pages: {[p.get('displayName', '') for p in pages]}
            Web URL: {selected_report.get('webUrl', '')}
            Streaming Support: {'Yes' if has_streaming else 'No'}

            Please provide a helpful response about this report and what insights it can provide.
            Mention that the user can access the full report at the web URL.
            {streaming_info}
            """

            ai_response = await call_gpt5(prompt)

            response_data = {
                "selected_report": report_name,
                "embed_token": embed_token_data.get('token', '') if embed_token_data else None,
                "has_streaming_datasets": has_streaming,
                "workspace_id": powerbi_service.workspace_id
            }

            return QueryResponse(
                success=True,
                query=request.query,
                response=ai_response if ai_response else f"Found report: {report_name}. Access it at: {selected_report.get('webUrl', '')}",
                reports=[{
                    'id': report_id,
                    'name': report_name,
                    'webUrl': selected_report.get('webUrl', ''),
                    'embedUrl': embed_url,
                    'pages': pages,
                    'has_streaming': has_streaming
                }],
                embed_url=embed_url,
                data=response_data
            )
        else:
            # List available reports with enhanced information
            report_list = "\n".join([f"- {r['name']} (ID: {r.get('id', 'N/A')})" for r in reports])
            response = f"""I found {len(reports)} reports in your workspace:
{report_list}

You can also:
- Use streaming datasets for real-time data
- Apply row-level security for personalized views
- Execute DAX queries for custom analysis

Please specify which report you'd like to see or what specific data you're looking for."""

            return QueryResponse(
                success=True,
                query=request.query,
                response=response,
                reports=reports
            )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        return QueryResponse(
            success=False,
            query=request.query,
            response=f"Error processing query: {str(e)}. Please check your PowerBI configuration and permissions.",
            data={"error": str(e), "workspace_id": powerbi_service.workspace_id if powerbi_service else None}
        )

# Real-time streaming endpoint
class StreamingDataPush(BaseModel):
    dataset_name: str
    table_name: str
    data: List[Dict[str, Any]]
    create_if_not_exists: bool = False

@app.post("/api/v1/streaming/push-data")
async def push_streaming_data(request: StreamingDataPush):
    """Push real-time data to streaming dataset"""
    try:
        logger.info(f"Pushing streaming data to {request.dataset_name}")

        # Check if dataset exists in cache
        if request.dataset_name in powerbi_service.streaming_datasets_cache:
            dataset_id = powerbi_service.streaming_datasets_cache[request.dataset_name]['id']
        elif request.create_if_not_exists:
            # Create basic schema from first data row
            if request.data:
                first_row = request.data[0]
                table_schema = {
                    "name": request.table_name,
                    "columns": [
                        {"name": key, "dataType": "String"} for key in first_row.keys()
                    ]
                }

                dataset = await powerbi_service.create_streaming_dataset(request.dataset_name, table_schema)
                dataset_id = dataset.get('id')
            else:
                raise Exception("Cannot create dataset without data sample")
        else:
            raise Exception(f"Dataset '{request.dataset_name}' not found. Set create_if_not_exists=true to create it.")

        # Push the data
        success = await powerbi_service.push_streaming_data(dataset_id, request.table_name, request.data)

        return {
            "success": success,
            "message": f"Pushed {len(request.data)} rows to {request.dataset_name}",
            "dataset_id": dataset_id
        }

    except Exception as e:
        logger.error(f"Error pushing streaming data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/streaming/datasets")
async def list_streaming_datasets():
    """List all streaming datasets"""
    try:
        datasets = await powerbi_service.get_streaming_datasets()
        return {"success": True, "streaming_datasets": datasets}
    except Exception as e:
        logger.error(f"Error listing streaming datasets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
