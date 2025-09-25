"""Query Endpoint"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.azure_ai_service import AzureAIService

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None
    model: Optional[str] = "gpt-5"

class QueryResponse(BaseModel):
    success: bool
    query: str
    response: str
    data: Optional[Dict] = None

ai_service = AzureAIService()

@router.post("/", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process a BI query"""
    try:
        response = await ai_service.process_query(request.query)
        
        return QueryResponse(
            success=True,
            query=request.query,
            response=response,
            data={"model_used": request.model}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
