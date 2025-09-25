"""Power BI Service with Enhanced Permissions, Streaming Support, and Error Handling"""
import aiohttp
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PowerBIService:
    def __init__(self):
        self.tenant_id = settings.powerbi_tenant_id
        self.client_id = settings.powerbi_client_id
        self.client_secret = settings.powerbi_client_secret
        self.workspace_id = settings.powerbi_workspace_id
        self.dataset_id = settings.powerbi_dataset_id
        self.api_url = settings.powerbi_api_url or "https://api.powerbi.com/v1.0/myorg"
        self.scope = settings.powerbi_scope or "https://analysis.windows.net/powerbi/api/.default"
        self.access_token = None
        self.token_expiry = None
        self.streaming_datasets_cache = {}

        # Enhanced scope for streaming datasets and admin operations
        self.enhanced_scope = "https://analysis.windows.net/powerbi/api/Dataset.ReadWrite.All https://analysis.windows.net/powerbi/api/Report.ReadWrite.All"

        # Initialize PubNub service for real-time notifications
        self.pubnub_service = None
        if settings.pubnub_enabled:
            try:
                from app.services.pubnub_service import PubNubService
                self.pubnub_service = PubNubService()
                logger.info("PubNub integration enabled for Power BI streaming")
            except Exception as e:
                logger.warning(f"Could not initialize PubNub service: {str(e)}")
        
    async def get_access_token(self, use_enhanced_scope: bool = False) -> str:
        """Get Power BI access token with enhanced permissions for streaming datasets"""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            logger.info("Using cached Power BI access token")
            return self.access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        scope = self.enhanced_scope if use_enhanced_scope else self.scope

        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': scope,
            'grant_type': 'client_credentials'
        }

        logger.info(f"Requesting Power BI token with scope: {scope}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data['access_token']
                        expires_in = token_data.get('expires_in', 3600)
                        self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                        logger.info(f"Successfully obtained Power BI token, expires in {expires_in} seconds")
                        return self.access_token
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get access token: {response.status} - {error_text}")
                        raise Exception(f"Power BI authentication failed: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error during token acquisition: {str(e)}")
            raise Exception(f"Failed to authenticate with Power BI: {str(e)}")
    
    async def get_datasets(self) -> List[Dict]:
        """Get all datasets in workspace with enhanced error handling"""
        try:
            token = await self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets"
            logger.info(f"Fetching datasets from: {url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        datasets = data.get('value', [])
                        logger.info(f"Successfully retrieved {len(datasets)} datasets")
                        return datasets
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.error(f"Permission denied accessing datasets: {error_text}")
                        raise Exception("Insufficient permissions to access datasets. Please check app registration permissions.")
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get datasets: {response.status} - {error_text}")
                        raise Exception(f"Failed to get datasets: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error in get_datasets: {str(e)}")
            raise

    async def execute_dax_query(self, dax_query: str, dataset_id: str = None) -> Dict:
        """Execute DAX query with fallback mechanisms and enhanced error handling"""
        dataset_id = dataset_id or self.dataset_id

        try:
            # Try with enhanced scope first for DAX query execution
            token = await self.get_access_token(use_enhanced_scope=True)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets/{dataset_id}/executeQueries"
            logger.info(f"Executing DAX query on dataset {dataset_id}")

            body = {
                "queries": [{"query": dax_query}],
                "serializerSettings": {
                    "includeNulls": True
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get('results', [{}])[0]
                        logger.info("DAX query executed successfully")
                        return result
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.warning(f"DAX query permission denied, trying fallback: {error_text}")
                        # Fallback to dataset refresh or report-based approach
                        return await self._execute_dax_fallback(dax_query, dataset_id)
                    else:
                        error_text = await response.text()
                        logger.error(f"DAX query failed: {response.status} - {error_text}")
                        raise Exception(f"Failed to execute DAX query: {response.status} - {error_text}")

        except Exception as e:
            logger.error(f"Error executing DAX query: {str(e)}")
            # Try fallback approach
            try:
                return await self._execute_dax_fallback(dax_query, dataset_id)
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {str(fallback_error)}")
                raise Exception(f"DAX query execution failed: {str(e)}")

    async def _execute_dax_fallback(self, dax_query: str, dataset_id: str) -> Dict:
        """Fallback method when direct DAX execution fails"""
        logger.info("Attempting DAX fallback through dataset refresh")

        try:
            # Get dataset information instead
            dataset_info = await self.get_dataset_info(dataset_id)
            return {
                "tables": [{"rows": [{"fallback": "DAX execution not permitted, using dataset info"}]}],
                "dataset_info": dataset_info,
                "fallback_used": True,
                "message": "Direct DAX execution not available, providing dataset information"
            }
        except Exception as e:
            logger.error(f"Fallback method failed: {str(e)}")
            raise Exception("All DAX execution methods failed")

    async def get_dataset_info(self, dataset_id: str) -> Dict:
        """Get detailed dataset information"""
        try:
            token = await self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets/{dataset_id}"
            logger.info(f"Fetching dataset info for: {dataset_id}")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Retrieved dataset info: {data.get('name', 'Unknown')}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get dataset info: {response.status} - {error_text}")
                        raise Exception(f"Failed to get dataset info: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error getting dataset info: {str(e)}")
            raise

    # STREAMING DATASET SUPPORT METHODS

    async def create_streaming_dataset(self, dataset_name: str, table_schema: Dict) -> Dict:
        """Create a streaming dataset for real-time data"""
        try:
            token = await self.get_access_token(use_enhanced_scope=True)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets"
            logger.info(f"Creating streaming dataset: {dataset_name}")

            dataset_definition = {
                "name": dataset_name,
                "tables": [table_schema],
                "defaultMode": "Streaming"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=dataset_definition) as response:
                    if response.status == 201:
                        data = await response.json()
                        dataset_id = data.get('id')
                        logger.info(f"Streaming dataset created successfully: {dataset_id}")

                        # Cache for later use
                        self.streaming_datasets_cache[dataset_name] = {
                            'id': dataset_id,
                            'created_at': datetime.now(),
                            'schema': table_schema
                        }

                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create streaming dataset: {response.status} - {error_text}")
                        raise Exception(f"Failed to create streaming dataset: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error creating streaming dataset: {str(e)}")
            raise

    async def push_streaming_data(self, dataset_id: str, table_name: str, data: List[Dict]) -> bool:
        """Push data to streaming dataset with PubNub real-time notifications"""
        try:
            token = await self.get_access_token(use_enhanced_scope=True)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets/{dataset_id}/tables/{table_name}/rows"
            logger.info(f"Pushing {len(data)} rows to streaming dataset {dataset_id}")

            body = {"rows": data}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == 200:
                        logger.info("Successfully pushed streaming data")

                        # Send real-time notification via PubNub if enabled
                        if self.pubnub_service and self.pubnub_service.is_enabled():
                            try:
                                # Find dataset name for channel
                                dataset_name = None
                                for name, cache_data in self.streaming_datasets_cache.items():
                                    if cache_data['id'] == dataset_id:
                                        dataset_name = name
                                        break

                                if dataset_name:
                                    channel_name = self.pubnub_service.create_streaming_channel_name(dataset_name)
                                    notification_data = {
                                        "dataset_id": dataset_id,
                                        "dataset_name": dataset_name,
                                        "table_name": table_name,
                                        "rows_count": len(data),
                                        "sample_data": data[:3] if len(data) > 3 else data,  # Send sample for preview
                                        "timestamp": datetime.now().isoformat()
                                    }

                                    await self.pubnub_service.publish_streaming_data_notification(
                                        channel_name, notification_data
                                    )
                                    logger.info(f"Published real-time notification to channel: {channel_name}")

                            except Exception as pubnub_error:
                                logger.warning(f"PubNub notification failed: {str(pubnub_error)}")

                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to push streaming data: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error pushing streaming data: {str(e)}")
            return False

    async def get_streaming_datasets(self) -> List[Dict]:
        """Get all streaming datasets in workspace"""
        try:
            datasets = await self.get_datasets()
            streaming_datasets = [ds for ds in datasets if ds.get('defaultMode') == 'Streaming']
            logger.info(f"Found {len(streaming_datasets)} streaming datasets")
            return streaming_datasets
        except Exception as e:
            logger.error(f"Error getting streaming datasets: {str(e)}")
            return []

    # ROW-LEVEL SECURITY METHODS

    async def generate_embed_token_with_rls(self, report_id: str, username: str, roles: List[str] = None) -> Dict:
        """Generate embed token with row-level security"""
        try:
            token = await self.get_access_token(use_enhanced_scope=True)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.api_url}/groups/{self.workspace_id}/reports/{report_id}/GenerateToken"
            logger.info(f"Generating RLS embed token for user: {username}")

            body = {
                "accessLevel": "View",
                "identities": [{
                    "username": username,
                    "roles": roles or [],
                    "datasets": [self.dataset_id] if self.dataset_id else []
                }]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"RLS embed token generated successfully for {username}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to generate RLS embed token: {response.status} - {error_text}")
                        raise Exception(f"Failed to generate RLS embed token: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error generating RLS embed token: {str(e)}")
            raise

    async def get_workspace_reports(self) -> List[Dict]:
        """Get all reports in workspace with comprehensive error handling"""
        try:
            token = await self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            url = f"{self.api_url}/groups/{self.workspace_id}/reports"
            logger.info(f"Fetching workspace reports from: {url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        reports = data.get('value', [])
                        logger.info(f"Successfully retrieved {len(reports)} reports")
                        return reports
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.error(f"Permission denied accessing reports: {error_text}")
                        raise Exception("Insufficient permissions to access reports. Please check app registration permissions.")
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get reports: {response.status} - {error_text}")
                        raise Exception(f"Failed to get reports: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error in get_workspace_reports: {str(e)}")
            raise

    async def refresh_dataset(self, dataset_id: str = None) -> bool:
        """Trigger dataset refresh"""
        dataset_id = dataset_id or self.dataset_id
        try:
            token = await self.get_access_token(use_enhanced_scope=True)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets/{dataset_id}/refreshes"
            logger.info(f"Triggering dataset refresh for: {dataset_id}")

            body = {"notifyOption": "MailOnFailure"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == 202:
                        logger.info("Dataset refresh triggered successfully")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to refresh dataset: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error refreshing dataset: {str(e)}")
            return False

    async def get_refresh_history(self, dataset_id: str = None) -> List[Dict]:
        """Get dataset refresh history"""
        dataset_id = dataset_id or self.dataset_id
        try:
            token = await self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            url = f"{self.api_url}/groups/{self.workspace_id}/datasets/{dataset_id}/refreshes"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('value', [])
                    else:
                        logger.error(f"Failed to get refresh history: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting refresh history: {str(e)}")
            return []
