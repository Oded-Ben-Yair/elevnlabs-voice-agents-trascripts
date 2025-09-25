"""
Streaming API Endpoints for Seekapa BI Agent.
Provides WebSocket, SSE, and HTTP streaming endpoints with load balancing
support and comprehensive error handling.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime, timedelta
import uuid

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, BackgroundTasks
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Mock classes for when FastAPI is not available
    class FastAPI: pass
    class WebSocket: pass
    class WebSocketDisconnect(Exception): pass
    class HTTPException(Exception): pass
    class StreamingResponse: pass
    class CORSMiddleware: pass
    class BaseModel: pass
    def Field(**kwargs): pass
    def Depends(func): return func

from ..copilot import copilot_manager, WebSocketConnection, Message
from ..services.sse_service import sse_manager, SSEEvent, SSEEventType
from ..services.kafka_service import get_kafka_service
from ..services.message_queue import get_rabbitmq_service
from ..services.data_pipeline import pipeline_manager, DataRecord, PipelineConfig
from ..middleware.circuit_breaker import circuit_breaker, get_circuit_breaker

logger = logging.getLogger(__name__)

# Pydantic models for API requests/responses

class StreamSubscriptionRequest(BaseModel):
    """Request model for stream subscriptions."""
    topics: List[str] = Field(..., description="List of topics to subscribe to")
    client_id: Optional[str] = Field(None, description="Client identifier")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters for stream data")
    max_events: Optional[int] = Field(None, description="Maximum number of events to receive")
    timeout: Optional[int] = Field(300, description="Connection timeout in seconds")

class QueryStreamRequest(BaseModel):
    """Request model for query streaming."""
    query: str = Field(..., description="SQL query to execute")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters")
    stream_mode: str = Field("incremental", description="Streaming mode: 'incremental' or 'batch'")
    batch_size: Optional[int] = Field(1000, description="Batch size for streaming results")

class DataIngestionRequest(BaseModel):
    """Request model for data ingestion."""
    data: List[Dict[str, Any]] = Field(..., description="Data records to ingest")
    source: str = Field(..., description="Data source identifier")
    pipeline: Optional[str] = Field("default", description="Processing pipeline name")
    async_processing: bool = Field(True, description="Whether to process asynchronously")

class StreamingMetricsResponse(BaseModel):
    """Response model for streaming metrics."""
    active_websocket_connections: int
    active_sse_connections: int
    total_events_sent: int
    events_per_second: float
    error_rate: float
    uptime_seconds: float

class StreamingHealthResponse(BaseModel):
    """Response model for streaming health check."""
    status: str
    websocket_health: Dict[str, Any]
    sse_health: Dict[str, Any]
    kafka_health: Optional[Dict[str, Any]]
    rabbitmq_health: Optional[Dict[str, Any]]
    pipeline_health: Dict[str, Any]

# Create FastAPI app for streaming endpoints
if FASTAPI_AVAILABLE:
    streaming_app = FastAPI(
        title="Seekapa BI Streaming API",
        description="Real-time streaming endpoints for BI data",
        version="1.0.0"
    )

    # Add CORS middleware
    streaming_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket endpoints

    @streaming_app.websocket("/ws/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        """Main WebSocket endpoint for real-time communication."""
        await websocket.accept()

        try:
            # Handle new connection through copilot manager
            await copilot_manager.handle_new_connection(websocket, client_id)

        except WebSocketDisconnect:
            logger.info(f"WebSocket client {client_id} disconnected")
        except Exception as e:
            logger.error(f"WebSocket error for client {client_id}: {e}")
            await websocket.close()

    @streaming_app.websocket("/ws/query-stream/{client_id}")
    async def query_stream_websocket(websocket: WebSocket, client_id: str):
        """WebSocket endpoint specifically for streaming query results."""
        await websocket.accept()

        try:
            while True:
                # Receive query request
                data = await websocket.receive_text()
                request_data = json.loads(data)

                query = request_data.get("query")
                params = request_data.get("params", {})
                stream_mode = request_data.get("stream_mode", "incremental")

                if not query:
                    await websocket.send_json({
                        "error": "Query is required"
                    })
                    continue

                # Stream query results
                await stream_query_results(websocket, client_id, query, params, stream_mode)

        except WebSocketDisconnect:
            logger.info(f"Query stream client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Query stream error for client {client_id}: {e}")
            await websocket.close()

    @circuit_breaker("query_stream", failure_threshold=5, recovery_timeout=30.0)
    async def stream_query_results(websocket: WebSocket, client_id: str,
                                 query: str, params: Dict[str, Any], stream_mode: str):
        """Stream query results to WebSocket client."""
        try:
            logger.info(f"Starting query stream for client {client_id}: {query}")

            # This would integrate with your actual query engine
            # For now, we'll simulate streaming results

            total_rows = 1000  # Mock total
            batch_size = 100

            for batch_start in range(0, total_rows, batch_size):
                batch_end = min(batch_start + batch_size, total_rows)

                # Simulate query execution delay
                await asyncio.sleep(0.1)

                # Create mock result batch
                batch_data = []
                for i in range(batch_start, batch_end):
                    batch_data.append({
                        "id": i,
                        "timestamp": datetime.utcnow().isoformat(),
                        "value": f"data_{i}",
                        "metric": i * 1.5
                    })

                # Send batch to client
                message = {
                    "type": "query_result_batch",
                    "query_id": str(uuid.uuid4()),
                    "batch_start": batch_start,
                    "batch_size": len(batch_data),
                    "total_rows": total_rows,
                    "data": batch_data,
                    "has_more": batch_end < total_rows
                }

                await websocket.send_json(message)

                # Check if client is still connected
                if websocket.client_state.value != 1:  # WebSocketState.CONNECTED
                    break

            # Send completion message
            await websocket.send_json({
                "type": "query_complete",
                "total_rows": total_rows,
                "message": "Query streaming completed"
            })

        except Exception as e:
            await websocket.send_json({
                "type": "query_error",
                "error": str(e)
            })
            raise

    # Server-Sent Events (SSE) endpoints

    @streaming_app.get("/sse/events/{client_id}")
    async def sse_events_endpoint(client_id: str, last_event_id: Optional[str] = None):
        """SSE endpoint for one-way event streaming."""

        async def event_stream():
            """Generate SSE event stream."""
            async for event_data in sse_manager.create_client_stream(client_id, last_event_id):
                yield event_data

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )

    @streaming_app.post("/sse/subscribe/{client_id}")
    async def sse_subscribe(client_id: str, request: StreamSubscriptionRequest):
        """Subscribe SSE client to specific topics."""
        try:
            for topic in request.topics:
                await sse_manager.subscribe_client_to_topic(client_id, topic)

            return {
                "success": True,
                "client_id": client_id,
                "subscribed_topics": request.topics,
                "message": "Successfully subscribed to topics"
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.post("/sse/unsubscribe/{client_id}")
    async def sse_unsubscribe(client_id: str, topics: List[str]):
        """Unsubscribe SSE client from specific topics."""
        try:
            for topic in topics:
                await sse_manager.unsubscribe_client_from_topic(client_id, topic)

            return {
                "success": True,
                "client_id": client_id,
                "unsubscribed_topics": topics,
                "message": "Successfully unsubscribed from topics"
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Data ingestion endpoints

    @streaming_app.post("/ingest/stream")
    async def ingest_stream_data(request: DataIngestionRequest, background_tasks: BackgroundTasks):
        """Ingest streaming data for real-time processing."""
        try:
            pipeline = pipeline_manager.get_pipeline(request.pipeline)
            if not pipeline:
                raise HTTPException(status_code=404, detail=f"Pipeline '{request.pipeline}' not found")

            ingested_count = 0
            failed_count = 0

            for data_item in request.data:
                try:
                    # Create data record
                    record = DataRecord(
                        data=data_item,
                        source=request.source,
                        metadata={
                            "ingestion_time": datetime.utcnow().isoformat(),
                            "client_source": request.source,
                            "pipeline": request.pipeline
                        }
                    )

                    # Add to pipeline for processing
                    if request.async_processing:
                        success = await pipeline.process_record(record)
                        if success:
                            ingested_count += 1
                        else:
                            failed_count += 1
                    else:
                        # Synchronous processing (for small datasets)
                        background_tasks.add_task(pipeline.process_record, record)
                        ingested_count += 1

                except Exception as e:
                    logger.error(f"Error ingesting record: {e}")
                    failed_count += 1

            return {
                "success": True,
                "ingested_count": ingested_count,
                "failed_count": failed_count,
                "pipeline": request.pipeline,
                "processing_mode": "async" if request.async_processing else "background"
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.post("/ingest/batch")
    async def ingest_batch_data(request: DataIngestionRequest):
        """Ingest batch data for processing."""
        try:
            # Process data in batches
            batch_size = 100
            total_records = len(request.data)
            processed_batches = 0

            for i in range(0, total_records, batch_size):
                batch = request.data[i:i + batch_size]

                # Process batch (mock implementation)
                await asyncio.sleep(0.1)  # Simulate processing time
                processed_batches += 1

            return {
                "success": True,
                "total_records": total_records,
                "processed_batches": processed_batches,
                "batch_size": batch_size,
                "processing_time": processed_batches * 0.1
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Event publishing endpoints

    @streaming_app.post("/events/publish")
    async def publish_event(topic: str, event_data: Dict[str, Any]):
        """Publish event to all subscribers."""
        try:
            # Create SSE event
            sse_event = SSEEvent(
                id=str(uuid.uuid4()),
                event="data",
                data=event_data
            )

            # Broadcast via SSE
            await sse_manager.broadcast_event(sse_event, topic)

            # Broadcast via WebSocket
            ws_message = Message(
                id=sse_event.id,
                type="event",
                data={
                    "topic": topic,
                    "event_data": event_data
                }
            )
            await copilot_manager.broadcast_message(ws_message)

            # Send to message queues if available
            kafka_service = get_kafka_service()
            if kafka_service:
                await kafka_service.send_event(topic, event_data)

            rabbitmq_service = get_rabbitmq_service()
            if rabbitmq_service:
                await rabbitmq_service.send_event(topic, event_data)

            return {
                "success": True,
                "event_id": sse_event.id,
                "topic": topic,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.post("/events/broadcast")
    async def broadcast_event(event_data: Dict[str, Any]):
        """Broadcast event to all connected clients."""
        try:
            event_id = str(uuid.uuid4())

            # Broadcast via SSE (all clients)
            sse_event = SSEEvent(
                id=event_id,
                event="broadcast",
                data=event_data
            )
            await sse_manager.broadcast_event(sse_event)

            # Broadcast via WebSocket (all clients)
            ws_message = Message(
                id=event_id,
                type="broadcast",
                data=event_data
            )
            await copilot_manager.broadcast_message(ws_message)

            return {
                "success": True,
                "event_id": event_id,
                "broadcast_type": "all_clients",
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Monitoring and management endpoints

    @streaming_app.get("/metrics", response_model=StreamingMetricsResponse)
    async def get_streaming_metrics():
        """Get streaming service metrics."""
        try:
            # WebSocket metrics
            ws_info = copilot_manager.get_all_connections_info()
            ws_stats = ws_info.get("statistics", {})

            # SSE metrics
            sse_stats = sse_manager.get_manager_stats()
            sse_statistics = sse_stats.get("statistics", {})

            # Calculate rates
            uptime = ws_stats.get("uptime_seconds", 0)
            events_per_second = (ws_stats.get("messages_sent", 0) + sse_statistics.get("total_events_sent", 0)) / max(uptime, 1)

            total_connections = ws_stats.get("active_connections", 0) + sse_stats.get("active_connections", 0)
            total_events = ws_stats.get("messages_sent", 0) + sse_statistics.get("total_events_sent", 0)
            total_errors = ws_stats.get("messages_failed", 0)  # Add SSE errors when available

            error_rate = total_errors / max(total_events, 1)

            return StreamingMetricsResponse(
                active_websocket_connections=ws_stats.get("active_connections", 0),
                active_sse_connections=sse_stats.get("active_connections", 0),
                total_events_sent=total_events,
                events_per_second=events_per_second,
                error_rate=error_rate,
                uptime_seconds=uptime
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.get("/health", response_model=StreamingHealthResponse)
    async def get_streaming_health():
        """Get streaming service health status."""
        try:
            # WebSocket health
            ws_health = await copilot_manager.health_check()

            # SSE health
            sse_health = await sse_manager.health_check()

            # External service health
            kafka_health = None
            kafka_service = get_kafka_service()
            if kafka_service:
                kafka_health = kafka_service.get_health_status()

            rabbitmq_health = None
            rabbitmq_service = get_rabbitmq_service()
            if rabbitmq_service:
                rabbitmq_health = rabbitmq_service.get_health_status()

            # Pipeline health
            pipeline_health = await pipeline_manager.health_check_all()

            # Determine overall status
            status = "healthy"
            if (ws_health.get("status") != "healthy" or
                sse_health.get("status") != "healthy" or
                any(p.get("status") != "healthy" for p in pipeline_health.values())):
                status = "degraded"

            return StreamingHealthResponse(
                status=status,
                websocket_health=ws_health,
                sse_health=sse_health,
                kafka_health=kafka_health,
                rabbitmq_health=rabbitmq_health,
                pipeline_health=pipeline_health
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.get("/connections")
    async def get_active_connections():
        """Get information about active connections."""
        try:
            # WebSocket connections
            ws_connections = copilot_manager.get_all_connections_info()

            # SSE connections
            sse_connections = sse_manager.get_manager_stats()

            return {
                "websocket_connections": ws_connections,
                "sse_connections": sse_connections,
                "summary": {
                    "total_websocket": len(ws_connections.get("active_connections", {})),
                    "total_sse": sse_connections.get("active_connections", 0),
                    "total_connections": (
                        len(ws_connections.get("active_connections", {})) +
                        sse_connections.get("active_connections", 0)
                    )
                }
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.post("/connections/{client_id}/disconnect")
    async def disconnect_client(client_id: str):
        """Forcefully disconnect a specific client."""
        try:
            # Disconnect from WebSocket
            ws_connection = copilot_manager.connections.get(client_id)
            if ws_connection:
                await copilot_manager.handle_disconnection(client_id)
                ws_disconnected = True
            else:
                ws_disconnected = False

            # Disconnect from SSE
            await sse_manager.remove_client(client_id)

            return {
                "success": True,
                "client_id": client_id,
                "websocket_disconnected": ws_disconnected,
                "sse_disconnected": True,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Circuit breaker management endpoints

    @streaming_app.get("/circuit-breakers")
    async def get_circuit_breaker_status():
        """Get status of all circuit breakers."""
        try:
            from ..middleware.circuit_breaker import get_all_circuit_breaker_metrics
            return get_all_circuit_breaker_metrics()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @streaming_app.post("/circuit-breakers/{breaker_name}/reset")
    async def reset_circuit_breaker_endpoint(breaker_name: str):
        """Reset a specific circuit breaker."""
        try:
            from ..middleware.circuit_breaker import reset_circuit_breaker
            success = await reset_circuit_breaker(breaker_name)

            if success:
                return {
                    "success": True,
                    "breaker_name": breaker_name,
                    "message": "Circuit breaker reset successfully"
                }
            else:
                raise HTTPException(status_code=404, detail=f"Circuit breaker '{breaker_name}' not found")

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Load balancing support endpoints

    @streaming_app.get("/load-balancer/status")
    async def get_load_balancer_status():
        """Get load balancer status and server information."""
        try:
            import socket
            import psutil

            # Get server information
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)

            # Get resource utilization
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Get connection counts
            ws_info = copilot_manager.get_all_connections_info()
            sse_info = sse_manager.get_manager_stats()

            active_connections = (
                ws_info.get("statistics", {}).get("active_connections", 0) +
                sse_info.get("active_connections", 0)
            )

            return {
                "server_id": hostname,
                "server_ip": local_ip,
                "status": "healthy",
                "active_connections": active_connections,
                "resource_utilization": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": (disk.used / disk.total) * 100
                },
                "connection_capacity": {
                    "websocket_connections": len(copilot_manager.connections),
                    "sse_connections": len(sse_manager.connections),
                    "max_recommended": 1000  # Configure based on server capacity
                },
                "uptime": time.time() - ws_info.get("statistics", {}).get("uptime_start", time.time())
            }

        except Exception as e:
            logger.error(f"Error getting load balancer status: {e}")
            return {
                "server_id": "unknown",
                "status": "error",
                "error": str(e)
            }

else:
    # Create a dummy app when FastAPI is not available
    class DummyStreamingApp:
        def __init__(self):
            logger.warning("FastAPI not available. Streaming API endpoints disabled.")

        def add_middleware(self, *args, **kwargs):
            pass

    streaming_app = DummyStreamingApp()

# Utility functions for external integration

async def initialize_streaming_services():
    """Initialize all streaming services."""
    try:
        # Initialize copilot manager (already initialized)
        logger.info("WebSocket copilot manager initialized")

        # Initialize SSE manager (already initialized)
        logger.info("SSE manager initialized")

        # Create default data pipelines
        default_pipeline_config = PipelineConfig(
            name="default",
            description="Default data processing pipeline",
            batch_size=100,
            parallelism=2
        )

        default_pipeline = pipeline_manager.create_pipeline(default_pipeline_config)

        # Add processors to default pipeline
        from ..services.data_pipeline import ValidationProcessor, TransformationProcessor, EnrichmentProcessor

        default_pipeline.add_processor(ValidationProcessor())
        default_pipeline.add_processor(TransformationProcessor())
        default_pipeline.add_processor(EnrichmentProcessor())

        # Start pipelines
        await pipeline_manager.start_all()

        logger.info("Streaming services initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Error initializing streaming services: {e}")
        return False

async def shutdown_streaming_services():
    """Shutdown all streaming services."""
    try:
        # Stop pipelines
        await pipeline_manager.stop_all()

        # Close connections would be handled by the web server
        logger.info("Streaming services shut down successfully")

    except Exception as e:
        logger.error(f"Error shutting down streaming services: {e}")

# Export the streaming app for mounting in main application
__all__ = ["streaming_app", "initialize_streaming_services", "shutdown_streaming_services"]