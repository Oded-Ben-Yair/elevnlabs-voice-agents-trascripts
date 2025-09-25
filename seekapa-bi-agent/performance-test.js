import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('error_rate');
const apiResponseTime = new Trend('api_response_time');
const requestsPerSecond = new Counter('requests_per_second');

export const options = {
  stages: [
    { duration: '1m', target: 50 },     // Warm up
    { duration: '2m', target: 100 },    // Ramp up to 100 users
    { duration: '3m', target: 500 },    // Ramp up to 500 users
    { duration: '2m', target: 1000 },   // Peak load at 1K users
    { duration: '1m', target: 1500 },   // Maximum load test
    { duration: '2m', target: 500 },    // Scale down
    { duration: '1m', target: 0 },      // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(50)<100', 'p(95)<200', 'p(99)<500'], // Response time targets
    http_req_failed: ['rate<0.01'],     // Less than 1% failures
    error_rate: ['rate<0.05'],          // Less than 5% errors
    api_response_time: ['p(95)<200'],   // 95th percentile under 200ms
  },
  ext: {
    loadimpact: {
      projectID: 3649135,
      name: "Seekapa BI Agent Performance Test"
    }
  }
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const FRONTEND_URL = __ENV.FRONTEND_URL || 'http://localhost:3000';

// Test data
const testQueries = [
  'Show me sales data',
  'What are the top performing products?',
  'Display customer analytics',
  'Show revenue trends',
  'Performance metrics dashboard',
  'Customer retention analysis',
  'Monthly sales report',
  'Product inventory status'
];

function getRandomQuery() {
  return testQueries[Math.floor(Math.random() * testQueries.length)];
}

export default function() {
  group('Health Checks', () => {
    // Test 1: Backend Health Check
    let healthResponse = http.get(`${BASE_URL}/health`);
    let healthCheck = check(healthResponse, {
      'backend health status is 200': (r) => r.status === 200,
      'backend health response time < 100ms': (r) => r.timings.duration < 100,
    });

    errorRate.add(!healthCheck);
    apiResponseTime.add(healthResponse.timings.duration);
    requestsPerSecond.add(1);

    // Test 2: Root Endpoint
    let rootResponse = http.get(`${BASE_URL}/`);
    let rootCheck = check(rootResponse, {
      'root endpoint status is 200': (r) => r.status === 200,
      'root response contains version': (r) => r.body.includes('version'),
    });

    errorRate.add(!rootCheck);
    apiResponseTime.add(rootResponse.timings.duration);
  });

  group('PowerBI API Tests', () => {
    // Test 3: PowerBI Connection Test
    let powerbiResponse = http.get(`${BASE_URL}/api/v1/powerbi/test-connection`);
    let powerbiCheck = check(powerbiResponse, {
      'PowerBI connection test status': (r) => r.status === 200 || r.status === 401, // 401 is expected without auth
    });

    errorRate.add(powerbiResponse.status >= 500);
    apiResponseTime.add(powerbiResponse.timings.duration);

    // Test 4: Streaming Datasets Endpoint
    let streamingResponse = http.get(`${BASE_URL}/api/v1/streaming/datasets`);
    let streamingCheck = check(streamingResponse, {
      'Streaming datasets endpoint responds': (r) => r.status < 500,
    });

    errorRate.add(streamingResponse.status >= 500);
    apiResponseTime.add(streamingResponse.timings.duration);
  });

  group('AI Query Processing', () => {
    // Test 5: AI Query Processing (Most Critical)
    const queryPayload = JSON.stringify({
      query: getRandomQuery(),
      model: 'gpt-5'
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
      },
    };

    let queryResponse = http.post(`${BASE_URL}/api/v1/query/`, queryPayload, params);
    let queryCheck = check(queryResponse, {
      'AI query status is 200': (r) => r.status === 200,
      'AI query response time < 2s': (r) => r.timings.duration < 2000,
      'AI query response contains success field': (r) => {
        try {
          let body = JSON.parse(r.body);
          return body.hasOwnProperty('success');
        } catch (e) {
          return false;
        }
      },
    });

    errorRate.add(!queryCheck);
    apiResponseTime.add(queryResponse.timings.duration);
    requestsPerSecond.add(1);
  });

  group('Frontend Tests', () => {
    // Test 6: Frontend Load Test
    let frontendResponse = http.get(FRONTEND_URL);
    let frontendCheck = check(frontendResponse, {
      'frontend loads successfully': (r) => r.status === 200,
      'frontend load time < 2s': (r) => r.timings.duration < 2000,
    });

    errorRate.add(!frontendCheck);
  });

  // Simulate user think time
  sleep(Math.random() * 2 + 1); // 1-3 second random delay
}

export function handleSummary(data) {
  const summary = {
    'test_start': data.state.testRunDurationMs,
    'vus_max': data.metrics.vus_max.values.max,
    'iterations': data.metrics.iterations.values.count,
    'http_reqs': data.metrics.http_reqs.values.count,
    'http_req_duration_p95': data.metrics.http_req_duration.values['p(95)'],
    'http_req_duration_p99': data.metrics.http_req_duration.values['p(99)'],
    'http_req_failed_rate': data.metrics.http_req_failed.values.rate,
    'data_received': data.metrics.data_received.values.count,
    'data_sent': data.metrics.data_sent.values.count,
    'checks_pass_rate': data.metrics.checks.values.rate,
  };

  return {
    'stdout': `
========== SEEKAPA BI AGENT PERFORMANCE RESULTS ==========
Test Duration: ${(data.state.testRunDurationMs / 1000).toFixed(2)}s
Max Virtual Users: ${summary.vus_max}
Total Iterations: ${summary.iterations}
Total HTTP Requests: ${summary.http_reqs}

RESPONSE TIMES:
- 95th Percentile: ${summary.http_req_duration_p95.toFixed(2)}ms
- 99th Percentile: ${summary.http_req_duration_p99.toFixed(2)}ms

ERROR RATES:
- HTTP Request Failures: ${(summary.http_req_failed_rate * 100).toFixed(2)}%
- Overall Check Pass Rate: ${(summary.checks_pass_rate * 100).toFixed(2)}%

DATA TRANSFER:
- Data Received: ${(summary.data_received / 1024 / 1024).toFixed(2)} MB
- Data Sent: ${(summary.data_sent / 1024).toFixed(2)} KB

TARGET VALIDATION:
- ✓ P95 Response Time Target (<200ms): ${summary.http_req_duration_p95 < 200 ? 'PASS' : 'FAIL'}
- ✓ P99 Response Time Target (<500ms): ${summary.http_req_duration_p99 < 500 ? 'PASS' : 'FAIL'}
- ✓ Error Rate Target (<1%): ${summary.http_req_failed_rate < 0.01 ? 'PASS' : 'FAIL'}
- ✓ Check Success Rate Target (>95%): ${summary.checks_pass_rate > 0.95 ? 'PASS' : 'FAIL'}
=========================================================
`,
    'performance-results.json': JSON.stringify(summary, null, 2),
  };
}