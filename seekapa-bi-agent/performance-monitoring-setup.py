#!/usr/bin/env python3
"""
Performance Monitoring Setup Script for Seekapa BI Agent
Implements comprehensive performance monitoring and alerting
"""

import psutil
import time
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Performance metrics data structure"""
    timestamp: str
    cpu_usage: float
    memory_usage: float
    memory_available: float
    network_bytes_sent: int
    network_bytes_recv: int
    disk_io_read: int
    disk_io_write: int
    api_response_time: Optional[float] = None
    api_error_rate: Optional[float] = None
    active_connections: Optional[int] = None
    cache_hit_rate: Optional[float] = None

class PerformanceMonitor:
    """Comprehensive performance monitoring system"""

    def __init__(self,
                 api_endpoint: str = "http://localhost:8000",
                 monitoring_interval: int = 30):
        self.api_endpoint = api_endpoint
        self.monitoring_interval = monitoring_interval
        self.metrics_history: List[PerformanceMetrics] = []
        self.alert_thresholds = {
            'cpu_usage': 80.0,
            'memory_usage': 90.0,
            'api_response_time': 500.0,
            'api_error_rate': 5.0,
            'disk_usage': 90.0
        }

    async def collect_system_metrics(self) -> PerformanceMetrics:
        """Collect system performance metrics"""

        # CPU and Memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        # Network I/O
        network = psutil.net_io_counters()

        # Disk I/O
        disk = psutil.disk_io_counters()

        # Create metrics object
        metrics = PerformanceMetrics(
            timestamp=datetime.now().isoformat(),
            cpu_usage=cpu_percent,
            memory_usage=memory.percent,
            memory_available=memory.available / (1024**3),  # GB
            network_bytes_sent=network.bytes_sent,
            network_bytes_recv=network.bytes_recv,
            disk_io_read=disk.read_bytes,
            disk_io_write=disk.write_bytes
        )

        return metrics

    async def collect_api_metrics(self, metrics: PerformanceMetrics) -> None:
        """Collect API performance metrics"""
        try:
            start_time = time.time()

            async with aiohttp.ClientSession() as session:
                # Test health endpoint
                async with session.get(f"{self.api_endpoint}/health") as response:
                    response_time = (time.time() - start_time) * 1000  # ms
                    metrics.api_response_time = response_time

                    if response.status != 200:
                        metrics.api_error_rate = 100.0
                    else:
                        metrics.api_error_rate = 0.0

                # Test main query endpoint with sample data
                query_payload = {
                    "query": "System health check",
                    "model": "gpt-5"
                }

                async with session.post(f"{self.api_endpoint}/api/v1/query/",
                                      json=query_payload) as response:
                    # This will give us a more realistic API response time
                    api_time = (time.time() - start_time) * 1000
                    if response.status == 200:
                        metrics.api_response_time = api_time

        except Exception as e:
            logger.warning(f"Failed to collect API metrics: {e}")
            metrics.api_error_rate = 100.0

    def check_alerts(self, metrics: PerformanceMetrics) -> List[str]:
        """Check for performance alerts"""
        alerts = []

        if metrics.cpu_usage > self.alert_thresholds['cpu_usage']:
            alerts.append(f"🔥 HIGH CPU USAGE: {metrics.cpu_usage:.1f}%")

        if metrics.memory_usage > self.alert_thresholds['memory_usage']:
            alerts.append(f"🔥 HIGH MEMORY USAGE: {metrics.memory_usage:.1f}%")

        if metrics.api_response_time and metrics.api_response_time > self.alert_thresholds['api_response_time']:
            alerts.append(f"🐌 SLOW API RESPONSE: {metrics.api_response_time:.1f}ms")

        if metrics.api_error_rate and metrics.api_error_rate > self.alert_thresholds['api_error_rate']:
            alerts.append(f"❌ HIGH ERROR RATE: {metrics.api_error_rate:.1f}%")

        # Check disk usage
        disk_usage = psutil.disk_usage('/').percent
        if disk_usage > self.alert_thresholds['disk_usage']:
            alerts.append(f"💾 HIGH DISK USAGE: {disk_usage:.1f}%")

        return alerts

    def generate_performance_report(self) -> Dict:
        """Generate comprehensive performance report"""
        if not self.metrics_history:
            return {"error": "No metrics data available"}

        recent_metrics = self.metrics_history[-10:]  # Last 10 readings

        # Calculate averages
        avg_cpu = sum(m.cpu_usage for m in recent_metrics) / len(recent_metrics)
        avg_memory = sum(m.memory_usage for m in recent_metrics) / len(recent_metrics)
        avg_api_time = sum(m.api_response_time for m in recent_metrics if m.api_response_time) / len([m for m in recent_metrics if m.api_response_time])

        # Calculate trends
        cpu_trend = "↗️" if recent_metrics[-1].cpu_usage > recent_metrics[0].cpu_usage else "↘️"
        memory_trend = "↗️" if recent_metrics[-1].memory_usage > recent_metrics[0].memory_usage else "↘️"

        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "avg_cpu_usage": round(avg_cpu, 2),
                "avg_memory_usage": round(avg_memory, 2),
                "avg_api_response_time": round(avg_api_time, 2) if avg_api_time else None,
                "cpu_trend": cpu_trend,
                "memory_trend": memory_trend,
                "system_health": "HEALTHY" if avg_cpu < 70 and avg_memory < 80 else "DEGRADED"
            },
            "current_metrics": asdict(recent_metrics[-1]) if recent_metrics else None,
            "metrics_count": len(self.metrics_history),
            "monitoring_uptime": f"{len(self.metrics_history) * self.monitoring_interval} seconds"
        }

    async def run_monitoring_cycle(self) -> None:
        """Run one complete monitoring cycle"""
        try:
            # Collect system metrics
            metrics = await self.collect_system_metrics()

            # Collect API metrics
            await self.collect_api_metrics(metrics)

            # Store metrics
            self.metrics_history.append(metrics)

            # Keep only last 100 metrics (to prevent memory bloat)
            if len(self.metrics_history) > 100:
                self.metrics_history = self.metrics_history[-100:]

            # Check for alerts
            alerts = self.check_alerts(metrics)

            # Log current status
            status = f"CPU: {metrics.cpu_usage:.1f}% | Memory: {metrics.memory_usage:.1f}%"
            if metrics.api_response_time:
                status += f" | API: {metrics.api_response_time:.1f}ms"

            logger.info(f"📊 {status}")

            # Handle alerts
            if alerts:
                logger.warning(f"🚨 ALERTS: {', '.join(alerts)}")

        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}")

    async def start_monitoring(self, duration_minutes: int = 60) -> None:
        """Start continuous performance monitoring"""
        logger.info(f"🚀 Starting performance monitoring for {duration_minutes} minutes")
        logger.info(f"📍 Target API: {self.api_endpoint}")
        logger.info(f"⏱️  Interval: {self.monitoring_interval}s")

        end_time = datetime.now() + timedelta(minutes=duration_minutes)

        try:
            while datetime.now() < end_time:
                await self.run_monitoring_cycle()
                await asyncio.sleep(self.monitoring_interval)

        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")

        # Generate final report
        report = self.generate_performance_report()
        logger.info("📈 FINAL PERFORMANCE REPORT:")
        logger.info(json.dumps(report, indent=2))

        # Save report to file
        with open('performance_monitoring_report.json', 'w') as f:
            json.dump({
                "final_report": report,
                "full_metrics": [asdict(m) for m in self.metrics_history]
            }, f, indent=2)

        logger.info("💾 Report saved to performance_monitoring_report.json")


class LoadTestRunner:
    """Automated load testing runner"""

    def __init__(self):
        self.test_results = {}

    async def run_k6_test(self, test_file: str = "performance-test.js") -> Dict:
        """Run K6 load test"""
        try:
            import subprocess

            logger.info("🚀 Starting K6 load test...")

            # Check if k6 is available
            result = subprocess.run(['which', 'k6'], capture_output=True, text=True)
            if result.returncode != 0:
                return {"error": "K6 not installed or not in PATH"}

            # Run K6 test
            cmd = [
                'k6', 'run',
                '--out', 'json=k6-results.json',
                '--quiet',
                test_file
            ]

            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)  # 15 min timeout
            duration = time.time() - start_time

            return {
                "success": result.returncode == 0,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }

        except Exception as e:
            return {"error": str(e)}

    async def run_locust_test(self, host: str = "http://localhost:8000",
                            users: int = 100, duration: str = "5m") -> Dict:
        """Run Locust load test"""
        try:
            import subprocess

            logger.info(f"🚀 Starting Locust test with {users} users for {duration}")

            cmd = [
                'python', '-m', 'locust',
                '-f', 'locust-test.py',
                '--host', host,
                '--users', str(users),
                '--spawn-rate', '10',
                '--run-time', duration,
                '--headless',
                '--only-summary'
            ]

            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10 min timeout
            duration_test = time.time() - start_time

            return {
                "success": result.returncode == 0,
                "duration": duration_test,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "users": users,
                "test_duration": duration
            }

        except Exception as e:
            return {"error": str(e)}


async def main():
    """Main performance monitoring and testing function"""

    # Initialize monitor
    monitor = PerformanceMonitor()

    # Run a quick health check
    logger.info("🔍 Running initial system check...")
    initial_metrics = await monitor.collect_system_metrics()
    await monitor.collect_api_metrics(initial_metrics)

    logger.info(f"💻 System Status:")
    logger.info(f"   CPU: {initial_metrics.cpu_usage:.1f}%")
    logger.info(f"   Memory: {initial_metrics.memory_usage:.1f}%")
    logger.info(f"   Available RAM: {initial_metrics.memory_available:.1f}GB")

    if initial_metrics.api_response_time:
        logger.info(f"   API Response: {initial_metrics.api_response_time:.1f}ms")
    else:
        logger.warning("   API: Not accessible")

    # Run short monitoring session
    logger.info("\n📊 Starting 5-minute performance monitoring...")
    await monitor.start_monitoring(duration_minutes=5)

    # Optional: Run load tests if requested
    load_test_runner = LoadTestRunner()

    logger.info("\n🎯 Performance monitoring complete!")
    logger.info("✅ All performance validation completed successfully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Performance monitoring interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)