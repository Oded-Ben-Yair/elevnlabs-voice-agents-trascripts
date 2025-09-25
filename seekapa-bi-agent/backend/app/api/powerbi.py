"""Enhanced Power BI API Endpoints with Streaming Support"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.services.powerbi_service import PowerBIService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
powerbi_service = PowerBIService()

# Pydantic models for request/response
class DAXQueryRequest(BaseModel):
    query: str
    dataset_id: Optional[str] = None

class StreamingDataRequest(BaseModel):
    dataset_id: str
    table_name: str
    data: List[Dict]

class CreateStreamingDatasetRequest(BaseModel):
    dataset_name: str
    table_schema: Dict

class RLSEmbedRequest(BaseModel):
    report_id: str
    username: str
    roles: Optional[List[str]] = None

@router.get("/datasets")
async def get_datasets():
    """Get all Power BI datasets"""
    try:
        datasets = await powerbi_service.get_datasets()
        return {"success": True, "datasets": datasets}
    except Exception as e:
        logger.error(f"Error getting datasets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/streaming-datasets")
async def get_streaming_datasets():
    """Get all streaming datasets"""
    try:
        datasets = await powerbi_service.get_streaming_datasets()
        return {"success": True, "streaming_datasets": datasets}
    except Exception as e:
        logger.error(f"Error getting streaming datasets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-streaming-dataset")
async def create_streaming_dataset(request: CreateStreamingDatasetRequest):
    """Create a new streaming dataset"""
    try:
        result = await powerbi_service.create_streaming_dataset(request.dataset_name, request.table_schema)
        return {"success": True, "dataset": result}
    except Exception as e:
        logger.error(f"Error creating streaming dataset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/push-streaming-data")
async def push_streaming_data(request: StreamingDataRequest):
    """Push data to streaming dataset"""
    try:
        success = await powerbi_service.push_streaming_data(request.dataset_id, request.table_name, request.data)
        return {"success": success, "message": "Data pushed successfully" if success else "Failed to push data"}
    except Exception as e:
        logger.error(f"Error pushing streaming data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute-dax")
async def execute_dax_query(request: DAXQueryRequest):
    """Execute DAX query with enhanced error handling"""
    try:
        result = await powerbi_service.execute_dax_query(request.query, request.dataset_id)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Error executing DAX query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reports")
async def get_reports():
    """Get all reports in workspace"""
    try:
        reports = await powerbi_service.get_workspace_reports()
        return {"success": True, "reports": reports}
    except Exception as e:
        logger.error(f"Error getting reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-rls-embed-token")
async def generate_rls_embed_token(request: RLSEmbedRequest):
    """Generate embed token with row-level security"""
    try:
        token_data = await powerbi_service.generate_embed_token_with_rls(
            request.report_id, request.username, request.roles
        )
        return {"success": True, "embed_token": token_data}
    except Exception as e:
        logger.error(f"Error generating RLS embed token: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dataset-info/{dataset_id}")
async def get_dataset_info(dataset_id: str):
    """Get detailed dataset information"""
    try:
        dataset_info = await powerbi_service.get_dataset_info(dataset_id)
        return {"success": True, "dataset_info": dataset_info}
    except Exception as e:
        logger.error(f"Error getting dataset info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh-dataset")
async def refresh_dataset(dataset_id: Optional[str] = None):
    """Trigger dataset refresh"""
    try:
        success = await powerbi_service.refresh_dataset(dataset_id)
        return {
            "success": success,
            "message": "Dataset refresh triggered" if success else "Failed to trigger refresh"
        }
    except Exception as e:
        logger.error(f"Error refreshing dataset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/refresh-history")
async def get_refresh_history(dataset_id: Optional[str] = Query(None)):
    """Get dataset refresh history"""
    try:
        history = await powerbi_service.get_refresh_history(dataset_id)
        return {"success": True, "refresh_history": history}
    except Exception as e:
        logger.error(f"Error getting refresh history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/test-connection")
async def test_connection():
    """Enhanced test Power BI connection with detailed diagnostics"""
    try:
        # Test basic token acquisition
        token = await powerbi_service.get_access_token()

        # Test workspace access
        reports = await powerbi_service.get_workspace_reports()
        datasets = await powerbi_service.get_datasets()

        return {
            "status": "connected",
            "token_received": bool(token),
            "workspace_accessible": True,
            "reports_count": len(reports),
            "datasets_count": len(datasets),
            "workspace_id": powerbi_service.workspace_id,
            "api_url": powerbi_service.api_url
        }
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")
        return {"status": "failed", "error": str(e)}
