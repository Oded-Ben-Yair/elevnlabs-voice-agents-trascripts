import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const loginRate = new Rate('login_success_rate');
const queryExecutionTime = new Trend('query_execution_time');
const apiErrors = new Counter('api_errors');
const concurrentUsers = new Counter('concurrent_users');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_URL = `${BASE_URL}/api`;

// Test data
const TEST_USERS = [
  { email: 'user1@example.com', password: 'password123' },
  { email: 'user2@example.com', password: 'password123' },
  { email: 'user3@example.com', password: 'password123' },
  { email: 'user4@example.com', password: 'password123' },
  { email: 'user5@example.com', password: 'password123' },
];

const SAMPLE_QUERIES = [
  'SELECT COUNT(*) FROM users',
  'SELECT * FROM users WHERE created_at > NOW() - INTERVAL 7 DAY',
  'SELECT u.username, COUNT(q.id) as query_count FROM users u LEFT JOIN queries q ON u.id = q.user_id GROUP BY u.id',
  'SELECT * FROM reports WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 50',
  'SELECT type, COUNT(*) as count FROM insights GROUP BY type',
];

// Load test scenarios
export let options = {
  scenarios: {
    // Smoke test - minimal load
    smoke_test: {
      executor: 'constant-vus',
      vus: 1,
      duration: '1m',
      tags: { test_type: 'smoke' },
    },

    // Load test - expected normal load
    load_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 10 },  // Ramp up
        { duration: '5m', target: 10 },  // Stay at 10 users
        { duration: '2m', target: 20 },  // Ramp up to 20 users
        { duration: '5m', target: 20 },  // Stay at 20 users
        { duration: '2m', target: 0 },   // Ramp down
      ],
      tags: { test_type: 'load' },
    },

    // Stress test - push beyond normal capacity
    stress_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },  // Ramp up to 50 users
        { duration: '5m', target: 50 },  // Stay at 50 users
        { duration: '2m', target: 100 }, // Ramp up to 100 users
        { duration: '5m', target: 100 }, // Stay at 100 users
        { duration: '3m', target: 0 },   // Ramp down
      ],
      tags: { test_type: 'stress' },
    },

    // Spike test - sudden load increase
    spike_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 10 },  // Normal load
        { duration: '30s', target: 200 }, // Spike to 200 users
        { duration: '1m', target: 200 },  // Stay at spike
        { duration: '30s', target: 10 },  // Back to normal
        { duration: '1m', target: 0 },    // Ramp down
      ],
      tags: { test_type: 'spike' },
    },
  },

  // Thresholds - performance criteria
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests under 500ms
    http_req_failed: ['rate<0.1'],    // Error rate under 10%
    login_success_rate: ['rate>0.95'], // Login success rate over 95%
    query_execution_time: ['p(90)<1000'], // 90% of queries under 1s
    api_errors: ['count<100'],        // Fewer than 100 API errors
  },
};

// Setup function - runs once before tests
export function setup() {
  console.log('Setting up load test...');

  // Health check
  const healthResponse = http.get(`${API_URL}/health`);
  if (healthResponse.status !== 200) {
    throw new Error(`API health check failed: ${healthResponse.status}`);
  }

  console.log('API is healthy, starting load test');
  return { api_url: API_URL };
}

// Main test function
export default function (data) {
  const user = TEST_USERS[randomIntBetween(0, TEST_USERS.length - 1)];
  let authToken;

  group('Authentication Flow', function () {
    // Login
    const loginPayload = {
      email: user.email,
      password: user.password,
    };

    const loginResponse = http.post(
      `${data.api_url}/auth/login`,
      JSON.stringify(loginPayload),
      {
        headers: {
          'Content-Type': 'application/json',
        },
        tags: { endpoint: 'login' },
      }
    );

    const loginSuccess = check(loginResponse, {
      'login status is 200': (r) => r.status === 200,
      'login response time < 1s': (r) => r.timings.duration < 1000,
      'has access token': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.data && body.data.access_token;
        } catch {
          return false;
        }
      },
    });

    loginRate.add(loginSuccess);

    if (loginSuccess) {
      const body = JSON.parse(loginResponse.body);
      authToken = body.data.access_token;
      concurrentUsers.add(1);
    } else {
      apiErrors.add(1);
      console.error(`Login failed for ${user.email}: ${loginResponse.status}`);
      return;
    }
  });

  if (authToken) {
    group('Query Operations', function () {
      // Create a new query
      const queryPayload = {
        query_text: SAMPLE_QUERIES[randomIntBetween(0, SAMPLE_QUERIES.length - 1)],
        params: {
          limit: randomIntBetween(10, 100),
          offset: randomIntBetween(0, 50),
        },
      };

      const createQueryResponse = http.post(
        `${data.api_url}/queries`,
        JSON.stringify(queryPayload),
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'create_query' },
        }
      );

      check(createQueryResponse, {
        'create query status is 201': (r) => r.status === 201,
        'create query response time < 2s': (r) => r.timings.duration < 2000,
      });

      let queryId;
      if (createQueryResponse.status === 201) {
        const body = JSON.parse(createQueryResponse.body);
        queryId = body.data.id;
      }

      // Execute the query
      if (queryId) {
        const executeStart = Date.now();
        const executeResponse = http.post(
          `${data.api_url}/queries/${queryId}/execute`,
          null,
          {
            headers: {
              'Authorization': `Bearer ${authToken}`,
            },
            tags: { endpoint: 'execute_query' },
          }
        );

        const executionTime = Date.now() - executeStart;
        queryExecutionTime.add(executionTime);

        check(executeResponse, {
          'execute query status is 200': (r) => r.status === 200,
          'execute query response time < 5s': (r) => r.timings.duration < 5000,
          'has query results': (r) => {
            try {
              const body = JSON.parse(r.body);
              return body.data && (body.data.rows || body.data.columns);
            } catch {
              return false;
            }
          },
        });

        if (executeResponse.status !== 200) {
          apiErrors.add(1);
        }
      }

      // Get user queries with pagination
      const getQueriesResponse = http.get(
        `${data.api_url}/queries?page=1&limit=20`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'get_queries' },
        }
      );

      check(getQueriesResponse, {
        'get queries status is 200': (r) => r.status === 200,
        'get queries response time < 1s': (r) => r.timings.duration < 1000,
      });
    });

    group('Report Operations', function () {
      // Create a report
      const reportPayload = {
        title: `Performance Test Report ${randomString(8)}`,
        description: 'Auto-generated report from load test',
        data: {
          charts: [
            {
              type: 'bar',
              data: Array.from({ length: 10 }, () => randomIntBetween(1, 100)),
            },
            {
              type: 'line',
              data: Array.from({ length: 20 }, () => randomIntBetween(1, 50)),
            },
          ],
          metadata: {
            generated_at: new Date().toISOString(),
            test_run: true,
          },
        },
      };

      const createReportResponse = http.post(
        `${data.api_url}/reports`,
        JSON.stringify(reportPayload),
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'create_report' },
        }
      );

      check(createReportResponse, {
        'create report status is 201': (r) => r.status === 201,
        'create report response time < 3s': (r) => r.timings.duration < 3000,
      });

      // Get user reports
      const getReportsResponse = http.get(
        `${data.api_url}/reports?page=1&limit=10`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'get_reports' },
        }
      );

      check(getReportsResponse, {
        'get reports status is 200': (r) => r.status === 200,
        'get reports response time < 1s': (r) => r.timings.duration < 1000,
      });
    });

    group('Analytics Operations', function () {
      // Get dashboard analytics
      const analyticsResponse = http.get(
        `${data.api_url}/analytics/dashboard`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'analytics_dashboard' },
        }
      );

      check(analyticsResponse, {
        'analytics status is 200': (r) => r.status === 200,
        'analytics response time < 2s': (r) => r.timings.duration < 2000,
        'has analytics data': (r) => {
          try {
            const body = JSON.parse(r.body);
            return body.data && body.data.total_queries !== undefined;
          } catch {
            return false;
          }
        },
      });

      // Get AI insights
      const insightsResponse = http.get(
        `${data.api_url}/analytics/insights`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'ai_insights' },
        }
      );

      check(insightsResponse, {
        'insights status is 200': (r) => r.status === 200,
        'insights response time < 1.5s': (r) => r.timings.duration < 1500,
      });
    });

    // Logout
    group('Cleanup', function () {
      const logoutResponse = http.post(
        `${data.api_url}/auth/logout`,
        null,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
          },
          tags: { endpoint: 'logout' },
        }
      );

      check(logoutResponse, {
        'logout status is 200': (r) => r.status === 200,
      });
    });
  }

  // Random sleep between 1-5 seconds to simulate user behavior
  sleep(randomIntBetween(1, 5));
}

// Teardown function - runs once after tests
export function teardown(data) {
  console.log('Load test completed');

  // Final health check
  const healthResponse = http.get(`${data.api_url}/health`);
  console.log(`Final API health status: ${healthResponse.status}`);
}

// Helper function for data validation
export function handleSummary(data) {
  console.log('=== Load Test Summary ===');
  console.log(`Total HTTP requests: ${data.metrics.http_reqs.values.count}`);
  console.log(`Failed HTTP requests: ${data.metrics.http_req_failed.values.rate * 100}%`);
  console.log(`Average response time: ${data.metrics.http_req_duration.values.avg}ms`);
  console.log(`95th percentile response time: ${data.metrics.http_req_duration.values['p(95)']}ms`);

  if (data.metrics.login_success_rate) {
    console.log(`Login success rate: ${data.metrics.login_success_rate.values.rate * 100}%`);
  }

  if (data.metrics.query_execution_time) {
    console.log(`Average query execution time: ${data.metrics.query_execution_time.values.avg}ms`);
    console.log(`90th percentile query execution time: ${data.metrics.query_execution_time.values['p(90)']}ms`);
  }

  if (data.metrics.api_errors) {
    console.log(`Total API errors: ${data.metrics.api_errors.values.count}`);
  }

  console.log('========================');

  // Return the summary for potential file output
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data, null, 2),
    'summary.html': htmlReport(data),
  };
}

// Generate text summary
function textSummary(data, options = {}) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let output = `${indent}Load Test Results\n`;
  output += `${indent}================\n\n`;

  // HTTP metrics
  output += `${indent}HTTP Metrics:\n`;
  output += `${indent}  Total Requests: ${data.metrics.http_reqs.values.count}\n`;
  output += `${indent}  Failed Requests: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  output += `${indent}  Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
  output += `${indent}  95th Percentile: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n\n`;

  // Custom metrics
  if (data.metrics.login_success_rate) {
    output += `${indent}Authentication:\n`;
    output += `${indent}  Login Success Rate: ${(data.metrics.login_success_rate.values.rate * 100).toFixed(2)}%\n\n`;
  }

  if (data.metrics.query_execution_time) {
    output += `${indent}Query Performance:\n`;
    output += `${indent}  Average Execution Time: ${data.metrics.query_execution_time.values.avg.toFixed(2)}ms\n`;
    output += `${indent}  90th Percentile: ${data.metrics.query_execution_time.values['p(90)'].toFixed(2)}ms\n\n`;
  }

  // Errors
  if (data.metrics.api_errors && data.metrics.api_errors.values.count > 0) {
    output += `${indent}Errors:\n`;
    output += `${indent}  Total API Errors: ${data.metrics.api_errors.values.count}\n\n`;
  }

  return output;
}

// Generate HTML report
function htmlReport(data) {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>K6 Load Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .metric { margin: 10px 0; padding: 10px; background: #f5f5f5; }
        .pass { color: green; }
        .fail { color: red; }
        .warn { color: orange; }
    </style>
</head>
<body>
    <h1>Load Test Report</h1>
    <div class="metric">
        <h3>HTTP Metrics</h3>
        <p>Total Requests: ${data.metrics.http_reqs.values.count}</p>
        <p>Failed Requests: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%</p>
        <p>Average Response Time: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms</p>
        <p>95th Percentile: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms</p>
    </div>

    ${data.metrics.login_success_rate ? `
    <div class="metric">
        <h3>Authentication</h3>
        <p>Login Success Rate: ${(data.metrics.login_success_rate.values.rate * 100).toFixed(2)}%</p>
    </div>
    ` : ''}

    ${data.metrics.query_execution_time ? `
    <div class="metric">
        <h3>Query Performance</h3>
        <p>Average Execution Time: ${data.metrics.query_execution_time.values.avg.toFixed(2)}ms</p>
        <p>90th Percentile: ${data.metrics.query_execution_time.values['p(90)'].toFixed(2)}ms</p>
    </div>
    ` : ''}

    <div class="metric">
        <h3>Thresholds</h3>
        ${Object.entries(data.root_group.checks || {}).map(([name, check]) =>
          `<p class="${check.passes === check.fails + check.passes ? 'pass' : 'fail'}">
             ${name}: ${check.passes}/${check.passes + check.fails}
           </p>`
        ).join('')}
    </div>
</body>
</html>`;
}