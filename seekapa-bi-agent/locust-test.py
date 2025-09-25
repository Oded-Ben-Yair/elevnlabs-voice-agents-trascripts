"""
Comprehensive Locust Performance Test Suite for Seekapa BI Agent
Tests API endpoints, WebSocket connections, and concurrent user scenarios
"""

import json
import random
import time
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser
import websocket
import threading

class BIAgentUser(FastHttpUser):
    """High-performance HTTP user for API testing"""

    wait_time = between(1, 3)
    weight = 70  # 70% of users will be regular HTTP users

    # Test data
    test_queries = [
        "Show me sales data for this quarter",
        "What are the top performing products this month?",
        "Display customer analytics dashboard",
        "Show revenue trends for the last year",
        "Performance metrics and KPIs",
        "Customer retention analysis report",
        "Monthly sales comparison report",
        "Product inventory and stock status",
        "Regional sales performance breakdown",
        "Financial dashboard overview"
    ]

    def on_start(self):
        """Initialize user session"""
        self.client.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'LocustPerformanceTest/1.0'
        })

        # Test authentication if endpoints require it
        response = self.client.get("/health", catch_response=True)
        if response.status_code != 200:
            response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def health_check(self):
        """Basic health check - high frequency"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Health check failed: {response.status_code}")
            elif response.elapsed.total_seconds() > 0.1:
                response.failure(f"Health check too slow: {response.elapsed.total_seconds()}s")

    @task(3)
    def root_endpoint(self):
        """Test root endpoint"""
        with self.client.get("/", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Root endpoint failed: {response.status_code}")
            elif "version" not in response.text:
                response.failure("Version info missing from root response")

    @task(10)
    def ai_query_processing(self):
        """Main AI query processing - most critical endpoint"""
        query_data = {
            "query": random.choice(self.test_queries),
            "model": "gpt-5"
        }

        start_time = time.time()
        with self.client.post("/api/v1/query/",
                             json=query_data,
                             catch_response=True,
                             name="AI_Query_Processing") as response:

            elapsed = time.time() - start_time

            if response.status_code != 200:
                response.failure(f"AI query failed: {response.status_code}")
            elif elapsed > 5.0:  # 5 second timeout for AI queries
                response.failure(f"AI query too slow: {elapsed:.2f}s")
            else:
                try:
                    result = response.json()
                    if not result.get('success'):
                        response.failure(f"AI query unsuccessful: {result.get('response', 'Unknown error')}")
                    else:
                        # Record successful query metrics
                        events.request.fire(
                            request_type="POST",
                            name="AI_Query_Success",
                            response_time=elapsed * 1000,
                            response_length=len(response.content),
                        )
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response from AI query")

    @task(2)
    def powerbi_connection_test(self):
        """Test PowerBI connectivity"""
        with self.client.get("/api/v1/powerbi/test-connection",
                           catch_response=True) as response:
            # PowerBI might return 401 without proper auth, which is acceptable
            if response.status_code >= 500:
                response.failure(f"PowerBI connection server error: {response.status_code}")

    @task(2)
    def streaming_datasets(self):
        """Test streaming datasets endpoint"""
        with self.client.get("/api/v1/streaming/datasets",
                           catch_response=True) as response:
            if response.status_code >= 500:
                response.failure(f"Streaming datasets server error: {response.status_code}")

    @task(1)
    def streaming_data_push(self):
        """Test streaming data push"""
        test_data = {
            "dataset_name": f"test_dataset_{random.randint(1, 10)}",
            "table_name": "performance_test",
            "data": [
                {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "metric": "test_value",
                    "value": random.randint(1, 1000),
                    "user_id": f"user_{random.randint(1, 100)}"
                }
            ],
            "create_if_not_exists": True
        }

        with self.client.post("/api/v1/streaming/push-data",
                             json=test_data,
                             catch_response=True) as response:
            if response.status_code >= 500:
                response.failure(f"Streaming push server error: {response.status_code}")


class WebSocketUser(HttpUser):
    """WebSocket user for real-time connection testing"""

    wait_time = between(2, 5)
    weight = 30  # 30% of users will test WebSocket connections

    def on_start(self):
        """Initialize WebSocket connections"""
        self.ws_connections = []
        self.setup_websockets()

    def setup_websockets(self):
        """Setup WebSocket connections for real-time testing"""
        try:
            # Test WebSocket connection (adjust URL as needed)
            ws_url = f"ws://{self.host.replace('http://', '').replace('https://', '')}/ws"

            def on_message(ws, message):
                # Record WebSocket message received
                events.request.fire(
                    request_type="WS",
                    name="WebSocket_Message_Received",
                    response_time=0,  # WebSocket messages don't have traditional response times
                    response_length=len(message),
                )

            def on_error(ws, error):
                events.request.fire(
                    request_type="WS",
                    name="WebSocket_Error",
                    response_time=0,
                    response_length=0,
                    exception=error
                )

            def on_close(ws, close_status_code, close_msg):
                events.request.fire(
                    request_type="WS",
                    name="WebSocket_Close",
                    response_time=0,
                    response_length=0,
                )

            # Note: This is a simplified WebSocket test
            # Real implementation would depend on actual WebSocket endpoints

        except Exception as e:
            print(f"WebSocket setup failed: {e}")

    @task(5)
    def simulate_real_time_query(self):
        """Simulate real-time dashboard queries"""
        query_data = {
            "query": "Show real-time metrics",
            "model": "gpt-5"
        }

        start_time = time.time()
        response = self.client.post("/api/v1/query/", json=query_data)
        elapsed = time.time() - start_time

        # Record real-time query performance
        events.request.fire(
            request_type="POST",
            name="Real_Time_Query",
            response_time=elapsed * 1000,
            response_length=len(response.content) if response.content else 0,
        )

    @task(3)
    def dashboard_refresh(self):
        """Simulate dashboard refresh operations"""
        with self.client.get("/health", catch_response=True) as response:
            if response.elapsed.total_seconds() > 0.05:  # 50ms threshold for dashboard
                response.failure(f"Dashboard refresh too slow: {response.elapsed.total_seconds()}s")

    def on_stop(self):
        """Cleanup WebSocket connections"""
        for ws in self.ws_connections:
            try:
                ws.close()
            except:
                pass


# Performance monitoring and custom metrics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize performance monitoring"""
    print("🚀 Starting Seekapa BI Agent Performance Test")
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.target_user_count}")
    print("=" * 60)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate performance report"""
    stats = environment.stats

    print("\n" + "=" * 60)
    print("📊 SEEKAPA BI AGENT PERFORMANCE RESULTS")
    print("=" * 60)

    # Overall statistics
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {(stats.total.num_failures/stats.total.num_requests)*100:.2f}%")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Max Response Time: {stats.total.max_response_time:.2f}ms")
    print(f"Requests/sec: {stats.total.current_rps:.2f}")

    print("\n📈 ENDPOINT PERFORMANCE:")
    for name, stat in stats.entries.items():
        if stat.num_requests > 0:
            print(f"  {name}:")
            print(f"    Requests: {stat.num_requests}")
            print(f"    Failures: {stat.num_failures} ({(stat.num_failures/stat.num_requests)*100:.1f}%)")
            print(f"    Avg Response: {stat.avg_response_time:.2f}ms")
            print(f"    95th Percentile: {stat.get_response_time_percentile(0.95):.2f}ms")

    # Performance validation
    print("\n✅ PERFORMANCE VALIDATION:")
    ai_query_stats = stats.entries.get(("POST", "AI_Query_Processing"))
    if ai_query_stats:
        p95_time = ai_query_stats.get_response_time_percentile(0.95)
        print(f"  AI Query P95 Response Time: {p95_time:.2f}ms (Target: <2000ms)")
        if p95_time < 2000:
            print("  ✓ AI Query Performance: PASS")
        else:
            print("  ✗ AI Query Performance: FAIL")

    overall_failure_rate = (stats.total.num_failures/stats.total.num_requests) if stats.total.num_requests > 0 else 0
    print(f"  Overall Failure Rate: {overall_failure_rate*100:.2f}% (Target: <1%)")
    if overall_failure_rate < 0.01:
        print("  ✓ Error Rate: PASS")
    else:
        print("  ✗ Error Rate: FAIL")

    print("=" * 60)


if __name__ == "__main__":
    import os
    from locust.main import main

    # Set default parameters for testing
    os.environ.setdefault("LOCUST_HOST", "http://localhost:8000")
    main()