"""PubNub Service for Real-time Messaging Integration with Power BI Streaming"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)

class PubNubService:
    """PubNub service for real-time messaging with Power BI integration"""

    def __init__(self):
        self.publish_key = settings.pubnub_publish_key
        self.subscribe_key = settings.pubnub_subscribe_key
        self.secret_key = settings.pubnub_secret_key
        self.enabled = settings.pubnub_enabled
        self.pubnub_instance = None

        if self.enabled and self.publish_key and self.subscribe_key:
            try:
                # Try to import PubNub - will be optional dependency
                from pubnub.pnconfiguration import PNConfiguration
                from pubnub.pubnub import PubNub

                config = PNConfiguration()
                config.publish_key = self.publish_key
                config.subscribe_key = self.subscribe_key
                if self.secret_key:
                    config.secret_key = self.secret_key
                config.ssl = True

                self.pubnub_instance = PubNub(config)
                logger.info("PubNub service initialized successfully")

            except ImportError:
                logger.warning("PubNub SDK not installed. Install with: pip install pubnub>=7.0.0")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize PubNub: {str(e)}")
                self.enabled = False
        else:
            logger.info("PubNub not configured or disabled")

    async def publish_streaming_data_notification(self, channel: str, data: Dict[str, Any]) -> bool:
        """Publish streaming data notification to PubNub channel"""
        if not self.enabled or not self.pubnub_instance:
            logger.debug("PubNub not enabled, skipping notification")
            return False

        try:
            message = {
                "type": "powerbi_streaming_data",
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "source": "seekapa_bi_agent"
            }

            # Publish message
            envelope = self.pubnub_instance.publish().channel(channel).message(message).sync()

            if envelope.status.is_error():
                logger.error(f"PubNub publish error: {envelope.status.error_data}")
                return False

            logger.info(f"Successfully published to PubNub channel: {channel}")
            return True

        except Exception as e:
            logger.error(f"Error publishing to PubNub: {str(e)}")
            return False

    async def publish_report_update(self, channel: str, report_data: Dict[str, Any]) -> bool:
        """Publish Power BI report update notification"""
        if not self.enabled:
            return False

        try:
            notification = {
                "type": "powerbi_report_update",
                "timestamp": datetime.now().isoformat(),
                "report": report_data,
                "source": "seekapa_bi_agent"
            }

            envelope = self.pubnub_instance.publish().channel(channel).message(notification).sync()
            return not envelope.status.is_error()

        except Exception as e:
            logger.error(f"Error publishing report update: {str(e)}")
            return False

    async def publish_query_result(self, channel: str, query: str, result: Dict[str, Any]) -> bool:
        """Publish query result to real-time subscribers"""
        if not self.enabled:
            return False

        try:
            message = {
                "type": "query_result",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "result": result,
                "source": "seekapa_bi_agent"
            }

            envelope = self.pubnub_instance.publish().channel(channel).message(message).sync()
            return not envelope.status.is_error()

        except Exception as e:
            logger.error(f"Error publishing query result: {str(e)}")
            return False

    def subscribe_to_channel(self, channel: str, callback):
        """Subscribe to PubNub channel for real-time updates"""
        if not self.enabled or not self.pubnub_instance:
            logger.warning("Cannot subscribe - PubNub not enabled")
            return None

        try:
            self.pubnub_instance.add_listener(callback)
            self.pubnub_instance.subscribe().channels(channel).execute()
            logger.info(f"Subscribed to PubNub channel: {channel}")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to channel: {str(e)}")
            return False

    def get_presence_info(self, channel: str) -> Optional[Dict]:
        """Get presence information for a channel"""
        if not self.enabled or not self.pubnub_instance:
            return None

        try:
            envelope = self.pubnub_instance.here_now().channels(channel).sync()
            if not envelope.status.is_error():
                return envelope.result.channels[0] if envelope.result.channels else None
            return None

        except Exception as e:
            logger.error(f"Error getting presence info: {str(e)}")
            return None

    def create_streaming_channel_name(self, dataset_name: str) -> str:
        """Create standardized channel name for streaming dataset"""
        safe_name = dataset_name.replace(" ", "_").replace("-", "_").lower()
        return f"powerbi_streaming_{safe_name}"

    def is_enabled(self) -> bool:
        """Check if PubNub service is enabled and configured"""
        return self.enabled and self.pubnub_instance is not None