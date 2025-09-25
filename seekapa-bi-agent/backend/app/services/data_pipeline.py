"""
Real-time Data Transformation Pipeline for Seekapa BI Agent.
Implements stream processing, data enrichment, validation, and transformation
with support for both batch and real-time processing.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable, Union, AsyncGenerator, Iterator
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import uuid
import hashlib
from collections import deque, defaultdict
import threading
import statistics
import pandas as pd
import numpy as np

try:
    from pydantic import BaseModel, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    class BaseModel: pass

logger = logging.getLogger(__name__)

class PipelineStage(Enum):
    INGESTION = "ingestion"
    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    ENRICHMENT = "enrichment"
    AGGREGATION = "aggregation"
    OUTPUT = "output"

class DataFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    AVRO = "avro"
    XML = "xml"

class ProcessingMode(Enum):
    STREAMING = "streaming"
    BATCH = "batch"
    MICRO_BATCH = "micro_batch"

@dataclass
class DataRecord:
    """Individual data record in the pipeline."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Optional[str] = None
    format: DataFormat = DataFormat.JSON
    processing_history: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_processing_step(self, step_name: str, success: bool = True, error: str = None):
        """Add processing step to history."""
        status = "SUCCESS" if success else "FAILED"
        self.processing_history.append(f"{step_name}:{status}:{datetime.utcnow().isoformat()}")
        if error:
            self.errors.append(error)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "id": self.id,
            "data": self.data,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "format": self.format.value,
            "processing_history": self.processing_history,
            "errors": self.errors
        }

@dataclass
class PipelineConfig:
    """Configuration for data pipeline."""
    name: str
    description: str = ""
    processing_mode: ProcessingMode = ProcessingMode.STREAMING
    batch_size: int = 100
    batch_timeout: float = 5.0  # seconds
    max_retries: int = 3
    error_threshold: float = 0.1  # 10% error threshold
    parallelism: int = 4

    # Buffer settings
    buffer_size: int = 1000
    buffer_timeout: float = 30.0

    # Monitoring settings
    enable_metrics: bool = True
    metrics_interval: float = 60.0

class PipelineMetrics:
    """Metrics collector for pipeline operations."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.records_processed = 0
        self.records_failed = 0
        self.processing_times = deque(maxlen=window_size)
        self.error_counts = defaultdict(int)
        self.stage_metrics = defaultdict(lambda: {"processed": 0, "failed": 0, "avg_time": 0.0})
        self.lock = threading.RLock()
        self.start_time = datetime.utcnow()

    def record_processing(self, stage: PipelineStage, duration: float, success: bool = True, error_type: str = None):
        """Record processing metrics."""
        with self.lock:
            self.records_processed += 1
            self.processing_times.append(duration)

            stage_key = stage.value
            self.stage_metrics[stage_key]["processed"] += 1

            if success:
                # Update average processing time
                current_avg = self.stage_metrics[stage_key]["avg_time"]
                current_count = self.stage_metrics[stage_key]["processed"]
                self.stage_metrics[stage_key]["avg_time"] = (
                    (current_avg * (current_count - 1) + duration) / current_count
                )
            else:
                self.records_failed += 1
                self.stage_metrics[stage_key]["failed"] += 1
                if error_type:
                    self.error_counts[error_type] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        with self.lock:
            total_processed = self.records_processed
            uptime = (datetime.utcnow() - self.start_time).total_seconds()

            return {
                "total_processed": total_processed,
                "total_failed": self.records_failed,
                "success_rate": (total_processed - self.records_failed) / max(total_processed, 1),
                "average_processing_time": statistics.mean(self.processing_times) if self.processing_times else 0.0,
                "throughput_per_second": total_processed / max(uptime, 1),
                "uptime_seconds": uptime,
                "stage_metrics": dict(self.stage_metrics),
                "error_distribution": dict(self.error_counts)
            }

class PipelineProcessor(ABC):
    """Abstract base class for pipeline processors."""

    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.metrics = PipelineMetrics()

    @abstractmethod
    async def process(self, record: DataRecord) -> Optional[DataRecord]:
        """Process a single data record."""
        pass

    async def process_batch(self, records: List[DataRecord]) -> List[DataRecord]:
        """Process a batch of records (default implementation processes one by one)."""
        results = []
        for record in records:
            result = await self.process(record)
            if result:
                results.append(result)
        return results

    def get_metrics(self) -> Dict[str, Any]:
        """Get processor metrics."""
        return {
            "processor": self.name,
            **self.metrics.get_metrics()
        }

class ValidationProcessor(PipelineProcessor):
    """Data validation processor."""

    def __init__(self, name: str = "validator", schema: Dict[str, Any] = None, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.schema = schema or {}

    async def process(self, record: DataRecord) -> Optional[DataRecord]:
        """Validate data record against schema."""
        start_time = time.time()

        try:
            # Basic validation
            if not record.data:
                raise ValueError("Empty data record")

            # Schema validation if provided
            if self.schema:
                await self._validate_schema(record)

            # Custom validation rules
            await self._validate_business_rules(record)

            duration = time.time() - start_time
            self.metrics.record_processing(PipelineStage.VALIDATION, duration, True)
            record.add_processing_step(self.name, True)

            return record

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Validation failed: {str(e)}"

            self.metrics.record_processing(PipelineStage.VALIDATION, duration, False, str(type(e).__name__))
            record.add_processing_step(self.name, False, error_msg)

            logger.warning(f"Validation failed for record {record.id}: {error_msg}")
            return None  # Drop invalid records

    async def _validate_schema(self, record: DataRecord):
        """Validate record against schema."""
        for field, field_type in self.schema.items():
            if field not in record.data:
                raise ValueError(f"Missing required field: {field}")

            if field_type == "string" and not isinstance(record.data[field], str):
                raise ValueError(f"Field {field} must be string")
            elif field_type == "number" and not isinstance(record.data[field], (int, float)):
                raise ValueError(f"Field {field} must be number")
            elif field_type == "boolean" and not isinstance(record.data[field], bool):
                raise ValueError(f"Field {field} must be boolean")

    async def _validate_business_rules(self, record: DataRecord):
        """Validate business-specific rules."""
        # Example business rules
        data = record.data

        # Check for negative values in numeric fields that shouldn't be negative
        negative_fields = ["revenue", "quantity", "price", "duration"]
        for field in negative_fields:
            if field in data and isinstance(data[field], (int, float)) and data[field] < 0:
                raise ValueError(f"Field {field} cannot be negative")

        # Check date ranges
        if "timestamp" in data:
            try:
                ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                if ts > datetime.utcnow():
                    raise ValueError("Timestamp cannot be in the future")
            except (ValueError, AttributeError):
                raise ValueError("Invalid timestamp format")

class TransformationProcessor(PipelineProcessor):
    """Data transformation processor."""

    def __init__(self, name: str = "transformer", transformations: List[Dict[str, Any]] = None, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.transformations = transformations or []

    async def process(self, record: DataRecord) -> Optional[DataRecord]:
        """Transform data record."""
        start_time = time.time()

        try:
            # Apply transformations
            for transformation in self.transformations:
                await self._apply_transformation(record, transformation)

            # Standard transformations
            await self._apply_standard_transformations(record)

            duration = time.time() - start_time
            self.metrics.record_processing(PipelineStage.TRANSFORMATION, duration, True)
            record.add_processing_step(self.name, True)

            return record

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Transformation failed: {str(e)}"

            self.metrics.record_processing(PipelineStage.TRANSFORMATION, duration, False, str(type(e).__name__))
            record.add_processing_step(self.name, False, error_msg)

            logger.error(f"Transformation failed for record {record.id}: {error_msg}")
            return record  # Return original record on transformation failure

    async def _apply_transformation(self, record: DataRecord, transformation: Dict[str, Any]):
        """Apply a specific transformation."""
        transform_type = transformation.get("type")
        field = transformation.get("field")

        if not field or field not in record.data:
            return

        if transform_type == "uppercase":
            if isinstance(record.data[field], str):
                record.data[field] = record.data[field].upper()

        elif transform_type == "lowercase":
            if isinstance(record.data[field], str):
                record.data[field] = record.data[field].lower()

        elif transform_type == "round":
            precision = transformation.get("precision", 2)
            if isinstance(record.data[field], (int, float)):
                record.data[field] = round(record.data[field], precision)

        elif transform_type == "multiply":
            factor = transformation.get("factor", 1)
            if isinstance(record.data[field], (int, float)):
                record.data[field] = record.data[field] * factor

        elif transform_type == "rename":
            new_name = transformation.get("new_name")
            if new_name and new_name != field:
                record.data[new_name] = record.data.pop(field)

        elif transform_type == "format_date":
            date_format = transformation.get("format", "%Y-%m-%d")
            if isinstance(record.data[field], str):
                try:
                    dt = datetime.fromisoformat(record.data[field].replace("Z", "+00:00"))
                    record.data[field] = dt.strftime(date_format)
                except (ValueError, AttributeError):
                    pass  # Keep original value if parsing fails

    async def _apply_standard_transformations(self, record: DataRecord):
        """Apply standard transformations."""
        data = record.data

        # Add derived fields
        if "created_at" not in data:
            data["created_at"] = datetime.utcnow().isoformat()

        if "record_hash" not in data:
            data_str = json.dumps(data, sort_keys=True)
            data["record_hash"] = hashlib.md5(data_str.encode()).hexdigest()

        # Clean string fields
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = value.strip()

class EnrichmentProcessor(PipelineProcessor):
    """Data enrichment processor."""

    def __init__(self, name: str = "enricher", enrichment_sources: Dict[str, Any] = None, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.enrichment_sources = enrichment_sources or {}
        self.cache = {}  # Simple cache for enrichment data

    async def process(self, record: DataRecord) -> Optional[DataRecord]:
        """Enrich data record with additional information."""
        start_time = time.time()

        try:
            # Apply enrichments
            await self._enrich_from_lookups(record)
            await self._enrich_with_calculations(record)
            await self._enrich_with_metadata(record)

            duration = time.time() - start_time
            self.metrics.record_processing(PipelineStage.ENRICHMENT, duration, True)
            record.add_processing_step(self.name, True)

            return record

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Enrichment failed: {str(e)}"

            self.metrics.record_processing(PipelineStage.ENRICHMENT, duration, False, str(type(e).__name__))
            record.add_processing_step(self.name, False, error_msg)

            logger.warning(f"Enrichment failed for record {record.id}: {error_msg}")
            return record  # Return original record on enrichment failure

    async def _enrich_from_lookups(self, record: DataRecord):
        """Enrich from lookup tables."""
        data = record.data

        # Example: User lookup
        if "user_id" in data and "user_name" not in data:
            user_name = await self._lookup_user_name(data["user_id"])
            if user_name:
                data["user_name"] = user_name

        # Example: Geographic enrichment
        if "ip_address" in data:
            geo_info = await self._lookup_geo_info(data["ip_address"])
            if geo_info:
                data.update(geo_info)

    async def _enrich_with_calculations(self, record: DataRecord):
        """Enrich with calculated fields."""
        data = record.data

        # Calculate derived metrics
        if "price" in data and "quantity" in data:
            try:
                data["total_amount"] = float(data["price"]) * float(data["quantity"])
            except (ValueError, TypeError):
                pass

        # Calculate time-based fields
        if "timestamp" in data:
            try:
                ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                data["hour_of_day"] = ts.hour
                data["day_of_week"] = ts.strftime("%A")
                data["is_weekend"] = ts.weekday() >= 5
            except (ValueError, AttributeError):
                pass

    async def _enrich_with_metadata(self, record: DataRecord):
        """Enrich with metadata."""
        data = record.data

        # Add processing metadata
        data["processed_at"] = datetime.utcnow().isoformat()
        data["processing_pipeline"] = self.config.get("pipeline_name", "default")

        # Add data quality metrics
        data["field_count"] = len([v for v in data.values() if v is not None])
        data["null_fields"] = len([v for v in data.values() if v is None])

    async def _lookup_user_name(self, user_id: str) -> Optional[str]:
        """Mock user lookup."""
        # In a real implementation, this would query a database or service
        user_cache_key = f"user_{user_id}"
        if user_cache_key in self.cache:
            return self.cache[user_cache_key]

        # Simulate lookup
        await asyncio.sleep(0.01)  # Simulate network delay
        user_name = f"User_{user_id[-4:]}"  # Mock name
        self.cache[user_cache_key] = user_name
        return user_name

    async def _lookup_geo_info(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Mock geo lookup."""
        # Mock geo enrichment
        return {
            "country": "US",
            "region": "California",
            "city": "San Francisco"
        }

class AggregationProcessor(PipelineProcessor):
    """Data aggregation processor."""

    def __init__(self, name: str = "aggregator", window_size: timedelta = None,
                 group_by: List[str] = None, metrics: List[str] = None, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.window_size = window_size or timedelta(minutes=5)
        self.group_by = group_by or []
        self.metrics = metrics or ["count", "sum", "avg"]
        self.windows = defaultdict(lambda: defaultdict(list))
        self.last_flush = datetime.utcnow()

    async def process(self, record: DataRecord) -> Optional[DataRecord]:
        """Process record for aggregation."""
        start_time = time.time()

        try:
            # Add to aggregation window
            await self._add_to_window(record)

            # Check if window should be flushed
            if datetime.utcnow() - self.last_flush >= self.window_size:
                aggregated_records = await self._flush_windows()
                self.last_flush = datetime.utcnow()

                if aggregated_records:
                    # Return the first aggregated record (in real implementation,
                    # you might want to yield all of them)
                    duration = time.time() - start_time
                    self.metrics.record_processing(PipelineStage.AGGREGATION, duration, True)
                    return aggregated_records[0]

            duration = time.time() - start_time
            self.metrics.record_processing(PipelineStage.AGGREGATION, duration, True)

            # Don't return the original record, as it's being aggregated
            return None

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Aggregation failed: {str(e)}"

            self.metrics.record_processing(PipelineStage.AGGREGATION, duration, False, str(type(e).__name__))
            record.add_processing_step(self.name, False, error_msg)

            logger.error(f"Aggregation failed for record {record.id}: {error_msg}")
            return record

    async def _add_to_window(self, record: DataRecord):
        """Add record to aggregation window."""
        if not self.group_by:
            group_key = "all"
        else:
            group_values = [str(record.data.get(field, "null")) for field in self.group_by]
            group_key = "|".join(group_values)

        window_key = self._get_window_key(record.timestamp)
        self.windows[window_key][group_key].append(record)

    def _get_window_key(self, timestamp: datetime) -> str:
        """Get window key for timestamp."""
        window_start = timestamp.replace(second=0, microsecond=0)
        minutes = (window_start.minute // 5) * 5  # 5-minute windows
        window_start = window_start.replace(minute=minutes)
        return window_start.isoformat()

    async def _flush_windows(self) -> List[DataRecord]:
        """Flush completed windows and create aggregated records."""
        current_time = datetime.utcnow()
        aggregated_records = []
        expired_windows = []

        for window_key, groups in self.windows.items():
            window_time = datetime.fromisoformat(window_key)
            if current_time - window_time >= self.window_size:
                expired_windows.append(window_key)

                for group_key, records in groups.items():
                    aggregated_record = await self._create_aggregated_record(window_key, group_key, records)
                    if aggregated_record:
                        aggregated_records.append(aggregated_record)

        # Clean up expired windows
        for window_key in expired_windows:
            del self.windows[window_key]

        return aggregated_records

    async def _create_aggregated_record(self, window_key: str, group_key: str, records: List[DataRecord]) -> DataRecord:
        """Create aggregated record from group of records."""
        if not records:
            return None

        # Extract numeric fields for aggregation
        numeric_fields = set()
        for record in records:
            for key, value in record.data.items():
                if isinstance(value, (int, float)):
                    numeric_fields.add(key)

        # Calculate aggregations
        aggregated_data = {
            "window_start": window_key,
            "group_key": group_key,
            "record_count": len(records)
        }

        # Add group by fields
        if self.group_by and group_key != "all":
            group_values = group_key.split("|")
            for i, field in enumerate(self.group_by):
                if i < len(group_values):
                    aggregated_data[field] = group_values[i]

        # Calculate metrics for numeric fields
        for field in numeric_fields:
            values = [float(r.data[field]) for r in records if field in r.data and isinstance(r.data[field], (int, float))]
            if values:
                if "sum" in self.metrics:
                    aggregated_data[f"{field}_sum"] = sum(values)
                if "avg" in self.metrics:
                    aggregated_data[f"{field}_avg"] = sum(values) / len(values)
                if "min" in self.metrics:
                    aggregated_data[f"{field}_min"] = min(values)
                if "max" in self.metrics:
                    aggregated_data[f"{field}_max"] = max(values)

        # Create aggregated record
        aggregated_record = DataRecord(
            data=aggregated_data,
            source=f"aggregation_{self.name}",
            metadata={
                "window_size": str(self.window_size),
                "source_record_count": len(records),
                "aggregation_timestamp": datetime.utcnow().isoformat()
            }
        )

        aggregated_record.add_processing_step(self.name, True)
        return aggregated_record

class DataPipeline:
    """Main data pipeline orchestrator."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.processors: List[PipelineProcessor] = []
        self.input_buffer = asyncio.Queue(maxsize=config.buffer_size)
        self.output_handlers: List[Callable] = []
        self.is_running = False
        self.worker_tasks: List[asyncio.Task] = []
        self.metrics = PipelineMetrics()

    def add_processor(self, processor: PipelineProcessor):
        """Add processor to pipeline."""
        self.processors.append(processor)

    def add_output_handler(self, handler: Callable):
        """Add output handler for processed records."""
        self.output_handlers.append(handler)

    async def start(self):
        """Start the pipeline."""
        if self.is_running:
            return

        self.is_running = True
        logger.info(f"Starting pipeline '{self.config.name}' with {self.config.parallelism} workers")

        # Start worker tasks
        for i in range(self.config.parallelism):
            task = asyncio.create_task(self._worker(f"worker_{i}"))
            self.worker_tasks.append(task)

        # Start metrics task if enabled
        if self.config.enable_metrics:
            metrics_task = asyncio.create_task(self._metrics_reporter())
            self.worker_tasks.append(metrics_task)

    async def stop(self):
        """Stop the pipeline."""
        if not self.is_running:
            return

        self.is_running = False
        logger.info(f"Stopping pipeline '{self.config.name}'")

        # Cancel worker tasks
        for task in self.worker_tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()

    async def process_record(self, record: DataRecord) -> bool:
        """Add record to processing queue."""
        try:
            await asyncio.wait_for(
                self.input_buffer.put(record),
                timeout=self.config.buffer_timeout
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Buffer full, dropping record {record.id}")
            return False

    async def _worker(self, worker_name: str):
        """Pipeline worker process."""
        logger.info(f"Pipeline worker {worker_name} started")

        while self.is_running:
            try:
                # Get record from buffer
                record = await asyncio.wait_for(
                    self.input_buffer.get(),
                    timeout=1.0
                )

                # Process record through pipeline
                await self._process_record_pipeline(record)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")

        logger.info(f"Pipeline worker {worker_name} stopped")

    async def _process_record_pipeline(self, record: DataRecord):
        """Process record through all processors."""
        start_time = time.time()
        current_record = record

        try:
            # Process through each processor
            for processor in self.processors:
                if current_record is None:
                    break

                current_record = await processor.process(current_record)

            # Send to output handlers if record survived processing
            if current_record:
                for handler in self.output_handlers:
                    try:
                        await handler(current_record)
                    except Exception as e:
                        logger.error(f"Output handler error: {e}")

            # Record metrics
            duration = time.time() - start_time
            success = current_record is not None and not current_record.errors
            self.metrics.record_processing(PipelineStage.OUTPUT, duration, success)

        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_processing(PipelineStage.OUTPUT, duration, False, str(type(e).__name__))
            logger.error(f"Pipeline processing failed for record {record.id}: {e}")

    async def _metrics_reporter(self):
        """Report pipeline metrics periodically."""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.metrics_interval)

                if self.config.enable_metrics:
                    metrics = self.get_metrics()
                    logger.info(f"Pipeline '{self.config.name}' metrics: {metrics}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics reporter error: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline metrics."""
        pipeline_metrics = self.metrics.get_metrics()
        processor_metrics = [p.get_metrics() for p in self.processors]

        return {
            "pipeline": self.config.name,
            "pipeline_metrics": pipeline_metrics,
            "processor_metrics": processor_metrics,
            "buffer_size": self.input_buffer.qsize(),
            "is_running": self.is_running,
            "worker_count": len(self.worker_tasks)
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on pipeline."""
        error_rate = self.metrics.records_failed / max(self.metrics.records_processed, 1)

        status = "healthy"
        if not self.is_running:
            status = "stopped"
        elif error_rate > self.config.error_threshold:
            status = "unhealthy"

        return {
            "status": status,
            "error_rate": error_rate,
            "error_threshold": self.config.error_threshold,
            "metrics": self.get_metrics()
        }

# Example output handlers
async def console_output_handler(record: DataRecord):
    """Output handler that prints to console."""
    print(f"Processed record {record.id}: {json.dumps(record.data, indent=2)}")

async def kafka_output_handler(record: DataRecord):
    """Output handler that sends to Kafka (mock implementation)."""
    logger.info(f"Sending record {record.id} to Kafka")
    # In real implementation, would use Kafka producer

# Global pipeline manager
class PipelineManager:
    """Manager for multiple data pipelines."""

    def __init__(self):
        self.pipelines: Dict[str, DataPipeline] = {}

    def create_pipeline(self, config: PipelineConfig) -> DataPipeline:
        """Create and register a new pipeline."""
        pipeline = DataPipeline(config)
        self.pipelines[config.name] = pipeline
        return pipeline

    def get_pipeline(self, name: str) -> Optional[DataPipeline]:
        """Get pipeline by name."""
        return self.pipelines.get(name)

    async def start_all(self):
        """Start all pipelines."""
        for pipeline in self.pipelines.values():
            await pipeline.start()

    async def stop_all(self):
        """Stop all pipelines."""
        for pipeline in self.pipelines.values():
            await pipeline.stop()

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all pipelines."""
        return {name: pipeline.get_metrics() for name, pipeline in self.pipelines.items()}

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Health check for all pipelines."""
        health_status = {}
        for name, pipeline in self.pipelines.items():
            health_status[name] = await pipeline.health_check()
        return health_status

# Global pipeline manager instance
pipeline_manager = PipelineManager()