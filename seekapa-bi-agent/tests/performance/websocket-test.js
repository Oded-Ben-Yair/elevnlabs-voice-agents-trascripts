import ws from 'k6/ws';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics for WebSocket testing
const wsConnections = new Counter('websocket_connections');
const wsConnectionErrors = new Counter('websocket_connection_errors');
const wsMessagesSent = new Counter('websocket_messages_sent');
const wsMessagesReceived = new Counter('websocket_messages_received');
const wsConnectionTime = new Trend('websocket_connection_time');
const wsMessageLatency = new Trend('websocket_message_latency');
const wsConnectionSuccess = new Rate('websocket_connection_success');

// Configuration
const WS_URL = __ENV.WS_URL || 'ws://localhost:8000/ws';

// Test scenarios for WebSocket connections
export let options = {
  scenarios: {
    // Test WebSocket connection stability
    websocket_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 10 },  // Ramp up to 10 connections
        { duration: '3m', target: 10 },  // Maintain 10 connections
        { duration: '1m', target: 20 },  // Increase to 20 connections
        { duration: '3m', target: 20 },  // Maintain 20 connections
        { duration: '1m', target: 0 },   // Ramp down
      ],
      tags: { test_type: 'websocket_load' },
    },

    // Test WebSocket connection bursts
    websocket_spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },   // Normal load
        { duration: '15s', target: 50 },  // Spike to 50 connections
        { duration: '1m', target: 50 },   // Maintain spike
        { duration: '15s', target: 5 },   // Back to normal
        { duration: '30s', target: 0 },   // Ramp down
      ],
      tags: { test_type: 'websocket_spike' },
    },
  },

  thresholds: {
    websocket_connection_success: ['rate>0.95'],
    websocket_connection_time: ['p(95)<1000'],
    websocket_message_latency: ['p(90)<100'],
    websocket_connection_errors: ['count<10'],
  },
};

export default function () {
  const clientId = `test-client-${__VU}-${__ITER}`;
  const connectionStart = Date.now();

  const response = ws.connect(
    `${WS_URL}?client_id=${clientId}`,
    {
      tags: { client_id: clientId },
    },
    function (socket) {
      const connectionTime = Date.now() - connectionStart;
      wsConnectionTime.add(connectionTime);
      wsConnections.add(1);
      wsConnectionSuccess.add(true);

      console.log(`WebSocket connected for client ${clientId}`);

      // Handle incoming messages
      socket.on('message', function (message) {
        wsMessagesReceived.add(1);

        try {
          const data = JSON.parse(message);

          // Measure message latency for heartbeat responses
          if (data.type === 'heartbeat_response' && data.data.client_timestamp) {
            const latency = Date.now() - data.data.client_timestamp;
            wsMessageLatency.add(latency);
          }

          console.log(`Received message: ${data.type} for client ${clientId}`);

          // Handle different message types
          switch (data.type) {
            case 'welcome':
              // Send initial query subscription
              const subscribeMessage = {
                id: `subscribe-${Date.now()}`,
                type: 'subscribe',
                data: {
                  topic: 'query-updates',
                  client_id: clientId,
                },
              };
              socket.send(JSON.stringify(subscribeMessage));
              wsMessagesSent.add(1);
              break;

            case 'heartbeat':
              // Respond to heartbeat
              const heartbeatResponse = {
                id: `heartbeat-response-${Date.now()}`,
                type: 'heartbeat_response',
                data: {
                  timestamp: Date.now(),
                  client_timestamp: data.data.timestamp,
                },
              };
              socket.send(JSON.stringify(heartbeatResponse));
              wsMessagesSent.add(1);
              break;

            case 'subscription_response':
              // Subscription confirmed, start sending queries
              setTimeout(() => {
                sendTestQuery(socket, clientId);
              }, 1000);
              break;
          }
        } catch (error) {
          console.error(`Error parsing message for client ${clientId}:`, error);
        }
      });

      // Handle connection errors
      socket.on('error', function (error) {
        console.error(`WebSocket error for client ${clientId}:`, error);
        wsConnectionErrors.add(1);
        wsConnectionSuccess.add(false);
      });

      // Handle connection close
      socket.on('close', function (code, reason) {
        console.log(`WebSocket closed for client ${clientId}: ${code} ${reason}`);
      });

      // Send periodic messages to test message handling
      const messageInterval = setInterval(() => {
        if (socket.readyState === 1) { // OPEN
          sendTestMessage(socket, clientId);
        }
      }, 5000); // Send a message every 5 seconds

      // Close connection after test duration
      setTimeout(() => {
        clearInterval(messageInterval);
        socket.close();
      }, 30000); // Close after 30 seconds
    }
  );

  // Check if connection was successful
  check(response, {
    'WebSocket connection established': (r) => r && r.status === 101,
  });

  if (!response || response.status !== 101) {
    wsConnectionErrors.add(1);
    wsConnectionSuccess.add(false);
  }
}

// Helper function to send test queries via WebSocket
function sendTestQuery(socket, clientId) {
  const queries = [
    'SELECT COUNT(*) FROM users',
    'SELECT * FROM queries WHERE user_id = ? LIMIT 10',
    'SELECT AVG(execution_time) FROM queries WHERE created_at > NOW() - INTERVAL 1 DAY',
    'SELECT type, COUNT(*) FROM insights GROUP BY type',
  ];

  const query = queries[Math.floor(Math.random() * queries.length)];

  const queryMessage = {
    id: `query-${Date.now()}-${Math.random()}`,
    type: 'query',
    data: {
      query: query,
      client_id: clientId,
      timestamp: Date.now(),
      params: {
        limit: Math.floor(Math.random() * 50) + 10,
      },
    },
  };

  if (socket.readyState === 1) {
    socket.send(JSON.stringify(queryMessage));
    wsMessagesSent.add(1);
    console.log(`Sent query for client ${clientId}: ${query}`);
  }
}

// Helper function to send test messages
function sendTestMessage(socket, clientId) {
  const messageTypes = [
    {
      type: 'ping',
      data: { timestamp: Date.now(), client_id: clientId },
    },
    {
      type: 'status_request',
      data: { client_id: clientId },
    },
    {
      type: 'custom_event',
      data: {
        event_type: 'user_action',
        action: 'page_view',
        client_id: clientId,
        timestamp: Date.now(),
      },
    },
  ];

  const message = messageTypes[Math.floor(Math.random() * messageTypes.length)];
  message.id = `msg-${Date.now()}-${Math.random()}`;

  if (socket.readyState === 1) {
    socket.send(JSON.stringify(message));
    wsMessagesSent.add(1);
  }
}

// Setup function
export function setup() {
  console.log('Starting WebSocket load test...');
  return { ws_url: WS_URL };
}

// Teardown function
export function teardown(data) {
  console.log('WebSocket load test completed');
  console.log(`Total WebSocket connections attempted: ${wsConnections}`);
  console.log(`Connection errors: ${wsConnectionErrors}`);
  console.log(`Messages sent: ${wsMessagesSent}`);
  console.log(`Messages received: ${wsMessagesReceived}`);
}

// Summary handler
export function handleSummary(data) {
  console.log('=== WebSocket Load Test Summary ===');

  if (data.metrics.websocket_connections) {
    console.log(`Total connections: ${data.metrics.websocket_connections.values.count}`);
  }

  if (data.metrics.websocket_connection_success) {
    console.log(`Connection success rate: ${(data.metrics.websocket_connection_success.values.rate * 100).toFixed(2)}%`);
  }

  if (data.metrics.websocket_connection_time) {
    console.log(`Average connection time: ${data.metrics.websocket_connection_time.values.avg.toFixed(2)}ms`);
    console.log(`95th percentile connection time: ${data.metrics.websocket_connection_time.values['p(95)'].toFixed(2)}ms`);
  }

  if (data.metrics.websocket_message_latency) {
    console.log(`Average message latency: ${data.metrics.websocket_message_latency.values.avg.toFixed(2)}ms`);
    console.log(`90th percentile message latency: ${data.metrics.websocket_message_latency.values['p(90)'].toFixed(2)}ms`);
  }

  if (data.metrics.websocket_messages_sent) {
    console.log(`Total messages sent: ${data.metrics.websocket_messages_sent.values.count}`);
  }

  if (data.metrics.websocket_messages_received) {
    console.log(`Total messages received: ${data.metrics.websocket_messages_received.values.count}`);
  }

  console.log('===================================');

  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'websocket-summary.json': JSON.stringify({
      timestamp: new Date().toISOString(),
      test_type: 'websocket_load_test',
      metrics: {
        connections: data.metrics.websocket_connections?.values,
        connection_success_rate: data.metrics.websocket_connection_success?.values,
        connection_time: data.metrics.websocket_connection_time?.values,
        message_latency: data.metrics.websocket_message_latency?.values,
        messages_sent: data.metrics.websocket_messages_sent?.values,
        messages_received: data.metrics.websocket_messages_received?.values,
        errors: data.metrics.websocket_connection_errors?.values,
      },
    }, null, 2),
  };
}

function textSummary(data, options = {}) {
  const indent = options.indent || '';
  let output = `${indent}WebSocket Load Test Results\n`;
  output += `${indent}===========================\n\n`;

  // Connection metrics
  if (data.metrics.websocket_connections) {
    output += `${indent}Connection Metrics:\n`;
    output += `${indent}  Total Connections: ${data.metrics.websocket_connections.values.count}\n`;

    if (data.metrics.websocket_connection_success) {
      output += `${indent}  Success Rate: ${(data.metrics.websocket_connection_success.values.rate * 100).toFixed(2)}%\n`;
    }

    if (data.metrics.websocket_connection_time) {
      output += `${indent}  Avg Connection Time: ${data.metrics.websocket_connection_time.values.avg.toFixed(2)}ms\n`;
      output += `${indent}  95th Percentile: ${data.metrics.websocket_connection_time.values['p(95)'].toFixed(2)}ms\n`;
    }

    output += '\n';
  }

  // Message metrics
  if (data.metrics.websocket_messages_sent || data.metrics.websocket_messages_received) {
    output += `${indent}Message Metrics:\n`;

    if (data.metrics.websocket_messages_sent) {
      output += `${indent}  Messages Sent: ${data.metrics.websocket_messages_sent.values.count}\n`;
    }

    if (data.metrics.websocket_messages_received) {
      output += `${indent}  Messages Received: ${data.metrics.websocket_messages_received.values.count}\n`;
    }

    if (data.metrics.websocket_message_latency) {
      output += `${indent}  Avg Message Latency: ${data.metrics.websocket_message_latency.values.avg.toFixed(2)}ms\n`;
      output += `${indent}  90th Percentile Latency: ${data.metrics.websocket_message_latency.values['p(90)'].toFixed(2)}ms\n`;
    }

    output += '\n';
  }

  // Error metrics
  if (data.metrics.websocket_connection_errors && data.metrics.websocket_connection_errors.values.count > 0) {
    output += `${indent}Errors:\n`;
    output += `${indent}  Connection Errors: ${data.metrics.websocket_connection_errors.values.count}\n\n`;
  }

  return output;
}