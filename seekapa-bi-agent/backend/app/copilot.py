"""Seekapa Copilot - Microsoft Copilot-style Power BI Assistant"""
import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import aiohttp
from dotenv import load_dotenv
import uuid

load_dotenv("../.env")

app = FastAPI(
    title="Seekapa Copilot",
    description="AI-Powered BI Assistant with Conversational Intelligence",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_AI_ENDPOINT = os.getenv("AZURE_AI_SERVICES_ENDPOINT")
GPT5_DEPLOYMENT = os.getenv("GPT5_DEPLOYMENT", "gpt-5")
POWERBI_TENANT_ID = os.getenv("POWERBI_TENANT_ID")
POWERBI_CLIENT_ID = os.getenv("POWERBI_CLIENT_ID")
POWERBI_CLIENT_SECRET = os.getenv("POWERBI_CLIENT_SECRET")
POWERBI_WORKSPACE_ID = "3260e688-0128-4e8b-b94c-76f9a42e877f"
POWERBI_API_URL = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"

# In-memory storage for conversations and insights
conversations = {}
insights_queue = []
pbi_token_cache = {"token": None, "expires": None}

class Message(BaseModel):
    content: str
    context: Optional[Dict] = None
    conversation_id: Optional[str] = None

class Insight(BaseModel):
    id: str
    title: str
    description: str
    severity: str  # "info", "warning", "critical"
    data: Dict
    timestamp: datetime
    actions: List[str]

class ConversationTurn(BaseModel):
    id: str
    user_message: str
    assistant_response: str
    data_context: Optional[Dict]
    timestamp: datetime
    suggestions: List[str]

async def get_powerbi_token():
    """Get Power BI access token"""
    global pbi_token_cache
    
    if pbi_token_cache["token"] and pbi_token_cache["expires"] and datetime.now() < pbi_token_cache["expires"]:
        return pbi_token_cache["token"]
    
    token_url = f"https://login.microsoftonline.com/{POWERBI_TENANT_ID}/oauth2/v2.0/token"
    data = {
        'client_id': POWERBI_CLIENT_ID,
        'client_secret': POWERBI_CLIENT_SECRET,
        'scope': POWERBI_SCOPE,
        'grant_type': 'client_credentials'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data) as resp:
            if resp.status == 200:
                token_data = await resp.json()
                pbi_token_cache["token"] = token_data['access_token']
                pbi_token_cache["expires"] = datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))
                return pbi_token_cache["token"]
            raise Exception("Failed to get Power BI token")

async def get_reports():
    """Get all Power BI reports"""
    try:
        token = await get_powerbi_token()
        headers = {'Authorization': f'Bearer {token}'}
        url = f"{POWERBI_API_URL}/groups/{POWERBI_WORKSPACE_ID}/reports"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('value', [])
    except Exception as e:
        print(f"Error getting reports: {e}")
    return []

async def analyze_data_context(query: str) -> Dict:
    """Analyze query to understand data context"""
    query_lower = query.lower()
    
    context = {
        "intent": "unknown",
        "timeframe": None,
        "metrics": [],
        "dimensions": [],
        "report_context": None
    }
    
    # Detect intent
    if any(word in query_lower for word in ["trend", "over time", "historical"]):
        context["intent"] = "trend_analysis"
    elif any(word in query_lower for word in ["compare", "versus", "vs", "difference"]):
        context["intent"] = "comparison"
    elif any(word in query_lower for word in ["top", "best", "highest", "lowest"]):
        context["intent"] = "ranking"
    elif any(word in query_lower for word in ["total", "sum", "count", "average"]):
        context["intent"] = "aggregation"
    elif any(word in query_lower for word in ["predict", "forecast", "will"]):
        context["intent"] = "prediction"
    
    # Detect timeframe
    if "today" in query_lower:
        context["timeframe"] = "today"
    elif "yesterday" in query_lower:
        context["timeframe"] = "yesterday"
    elif "this week" in query_lower:
        context["timeframe"] = "current_week"
    elif "this month" in query_lower:
        context["timeframe"] = "current_month"
    elif "this year" in query_lower:
        context["timeframe"] = "current_year"
    elif "last month" in query_lower:
        context["timeframe"] = "previous_month"
    
    # Detect metrics
    if any(word in query_lower for word in ["sales", "revenue"]):
        context["metrics"].append("sales")
    if any(word in query_lower for word in ["customer", "client"]):
        context["metrics"].append("customers")
    if any(word in query_lower for word in ["product", "item"]):
        context["metrics"].append("products")
    if any(word in query_lower for word in ["conversion", "rate"]):
        context["metrics"].append("conversion")
    
    return context

async def generate_suggestions(context: Dict) -> List[str]:
    """Generate contextual follow-up suggestions"""
    suggestions = []
    
    if context["intent"] == "trend_analysis":
        suggestions.extend([
            "Show me the forecast for next month",
            "What factors are driving this trend?",
            "Compare this to the same period last year"
        ])
    elif context["intent"] == "comparison":
        suggestions.extend([
            "What's the percentage difference?",
            "Show me the breakdown by category",
            "Which segment is performing better?"
        ])
    elif context["intent"] == "ranking":
        suggestions.extend([
            "Show me the bottom performers",
            "What's the distribution across all items?",
            "How has the ranking changed over time?"
        ])
    elif context["intent"] == "aggregation":
        suggestions.extend([
            "Break this down by region",
            "Show me the monthly trend",
            "What's the year-over-year growth?"
        ])
    else:
        suggestions.extend([
            "Show me total sales",
            "What are the top products?",
            "How are we performing this month?"
        ])
    
    return suggestions[:3]  # Return top 3 suggestions

async def call_gpt5_streaming(messages: List[Dict]):
    """Call GPT-5 with streaming response"""
    headers = {
        "api-key": AZURE_OPENAI_API_KEY,
        "Content-Type": "application/json"
    }
    
    url = f"{AZURE_AI_ENDPOINT}/openai/deployments/{GPT5_DEPLOYMENT}/chat/completions?api-version=2025-01-01-preview"
    
    system_message = {
        "role": "system",
        "content": """You are Seekapa Copilot, an intelligent business analytics assistant inspired by Microsoft Copilot for Power BI.

Your personality:
- Professional yet conversational
- Proactive in suggesting insights
- Clear and concise in explanations
- Focused on actionable intelligence

Your capabilities:
- Analyze business data and trends
- Generate insights from Power BI reports
- Provide predictive analytics
- Suggest next best actions
- Explain complex metrics simply

Always:
- Start responses directly without pleasantries
- Use data to support insights
- Suggest follow-up questions
- Highlight important findings with emphasis
- Keep responses concise (2-3 sentences for simple queries, 1 paragraph for complex)

Format insights using:
- **Bold** for key metrics
- Numbers and percentages prominently
- Clear cause-effect relationships
- Actionable recommendations"""
    }
    
    body = {
        "messages": [system_message] + messages,
        "max_completion_tokens": 800,
        "stream": True
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            if resp.status == 200:
                async for line in resp.content:
                    if line:
                        yield line
            else:
                yield b"Unable to process your request at this moment."

async def call_gpt5(messages: List[Dict]) -> str:
    """Call GPT-5 without streaming"""
    headers = {
        "api-key": AZURE_OPENAI_API_KEY,
        "Content-Type": "application/json"
    }
    
    url = f"{AZURE_AI_ENDPOINT}/openai/deployments/{GPT5_DEPLOYMENT}/chat/completions?api-version=2025-01-01-preview"
    
    system_message = {
        "role": "system",
        "content": """You are Seekapa Copilot, an intelligent business analytics assistant inspired by Microsoft Copilot for Power BI.

Your personality:
- Professional yet conversational
- Proactive in suggesting insights
- Clear and concise in explanations
- Focused on actionable intelligence

Your capabilities:
- Analyze business data and trends
- Generate insights from Power BI reports
- Provide predictive analytics
- Suggest next best actions
- Explain complex metrics simply

Always:
- Start responses directly without pleasantries
- Use data to support insights
- Suggest follow-up questions
- Highlight important findings with emphasis
- Keep responses concise (2-3 sentences for simple queries, 1 paragraph for complex)

Format insights using:
- **Bold** for key metrics
- Numbers and percentages prominently
- Clear cause-effect relationships
- Actionable recommendations"""
    }
    
    body = {
        "messages": [system_message] + messages,
        "max_completion_tokens": 800,
        "stream": False
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('choices', [{}])[0].get('message', {}).get('content', 'Unable to process your request.')
                else:
                    error_text = await resp.text()
                    print(f"GPT-5 API error: {resp.status} - {error_text}")
                    return "Unable to process your request at this moment."
    except Exception as e:
        print(f"Error calling GPT-5: {e}")
        return "I'm having trouble connecting to the AI service. Please try again."

async def detect_anomalies() -> List[Insight]:
    """Detect anomalies in data and generate insights"""
    insights = []
    
    # Simulated anomaly detection (in production, this would analyze real data)
    current_hour = datetime.now().hour
    
    if current_hour >= 8 and current_hour <= 10:  # Morning insight
        insights.append(Insight(
            id=str(uuid.uuid4()),
            title="Morning Sales Spike Detected",
            description="Sales are **35% higher** than typical Monday mornings. Customer activity peaked at 8:45 AM.",
            severity="info",
            data={"sales_increase": 35, "peak_time": "8:45 AM"},
            timestamp=datetime.now(),
            actions=["View detailed breakdown", "Compare with last Monday", "Analyze customer segments"]
        ))
    
    if current_hour >= 13 and current_hour <= 15:  # Afternoon alert
        insights.append(Insight(
            id=str(uuid.uuid4()),
            title="Conversion Rate Below Target",
            description="Current conversion rate is **2.3%**, below the 3% target. Mobile traffic showing lowest conversion.",
            severity="warning",
            data={"current_rate": 2.3, "target_rate": 3.0, "problem_channel": "mobile"},
            timestamp=datetime.now(),
            actions=["Analyze mobile UX", "Review checkout funnel", "Compare channel performance"]
        ))
    
    return insights

@app.get("/")
async def root():
    return {
        "name": "Seekapa Copilot",
        "version": "3.0.0",
        "status": "ready",
        "style": "Microsoft Copilot for Power BI"
    }

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = []
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            
            # Analyze context
            context = await analyze_data_context(user_message)
            
            # Get relevant reports
            reports = await get_reports()
            relevant_report = None
            if reports and context["metrics"]:
                for report in reports:
                    if any(metric in report.get('name', '').lower() for metric in context["metrics"]):
                        relevant_report = report
                        break
            
            # Prepare conversation context
            messages = [{"role": "user", "content": user_message}]
            if conversations[conversation_id]:
                # Add last 3 turns for context
                for turn in conversations[conversation_id][-3:]:
                    messages.insert(0, {"role": "assistant", "content": turn["assistant_response"]})
                    messages.insert(0, {"role": "user", "content": turn["user_message"]})
            
            # Get AI response (non-streaming for WebSocket)
            ai_response = await call_gpt5(messages)
            
            # Generate suggestions
            suggestions = await generate_suggestions(context)
            
            # Store conversation turn
            turn = {
                "user_message": user_message,
                "assistant_response": ai_response,
                "context": context,
                "suggestions": suggestions,
                "timestamp": datetime.now().isoformat()
            }
            conversations[conversation_id].append(turn)
            
            # Send response
            response = {
                "type": "response",
                "message": ai_response,
                "suggestions": suggestions,
                "context": context,
                "report": relevant_report
            }
            
            await websocket.send_json(response)
            
    except WebSocketDisconnect:
        if conversation_id in conversations:
            del conversations[conversation_id]

@app.get("/api/insights/latest")
async def get_latest_insights():
    """Get latest insights and anomalies"""
    insights = await detect_anomalies()
    return {"insights": [insight.dict() for insight in insights]}

@app.get("/api/insights/subscribe")
async def subscribe_to_insights():
    """Server-sent events for real-time insights"""
    async def generate():
        while True:
            insights = await detect_anomalies()
            if insights:
                for insight in insights:
                    yield f"data: {json.dumps(insight.dict())}\n\n"
            await asyncio.sleep(30)  # Check every 30 seconds
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/chat/message")
async def process_message(message: Message):
    """Process a single message (REST alternative to WebSocket)"""
    context = await analyze_data_context(message.content)
    
    messages = [{"role": "user", "content": message.content}]
    ai_response = await call_gpt5(messages)
    
    suggestions = await generate_suggestions(context)
    
    return {
        "response": ai_response,
        "suggestions": suggestions,
        "context": context
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
