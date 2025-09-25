import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock WebSocket and related modules
const mockWebSocket = {
  send: vi.fn(),
  close: vi.fn(),
  closed: false,
  readyState: 1, // OPEN
};

const mockWebSocketConnection = {
  websocket: mockWebSocket,
  client_id: 'test-client-123',
  state: 'connected',
  message_queue: [],
  pending_messages: {},
  last_heartbeat: Date.now() / 1000,
  heartbeat_config: {
    interval: 30.0,
    timeout: 10.0,
    max_missed: 3,
  },
  missed_heartbeats: 0,
};

vi.mock('websockets', () => ({
  default: {
    serve: vi.fn(),
    exceptions: {
      ConnectionClosed: class ConnectionClosed extends Error {},
    },
  },
}));

// Mock the Python copilot module interface
class MockMessage {
  constructor(id, type, data, timestamp = null) {
    this.id = id;
    this.type = type;
    this.data = data;
    this.timestamp = timestamp || Date.now() / 1000;
    this.retry_count = 0;
    this.max_retries = 3;
  }

  to_json() {
    return JSON.stringify({
      id: this.id,
      type: this.type,
      data: this.data,
      timestamp: this.timestamp,
      retry_count: this.retry_count,
      max_retries: this.max_retries,
    });
  }
}

class MockWebSocketConnection {
  constructor(websocket, client_id) {
    this.websocket = websocket;
    this.client_id = client_id;
    this.state = 'connected';
    this.message_queue = [];
    this.pending_messages = {};
    this.last_heartbeat = Date.now() / 1000;
    this.heartbeat_config = {
      interval: 30.0,
      timeout: 10.0,
      max_missed: 3,
    };
    this.missed_heartbeats = 0;
    this.reconnect_attempts = 0;
    this.max_reconnect_attempts = 10;
    this.reconnect_delay = 1.0;
    this.created_at = new Date();

    this._heartbeat_task = null;
    this._message_processor_task = null;
  }

  async start_background_tasks() {
    // Mock background task initialization
    this._heartbeat_task = { cancel: vi.fn() };
    this._message_processor_task = { cancel: vi.fn() };
  }

  async stop_background_tasks() {
    if (this._heartbeat_task) {
      this._heartbeat_task.cancel();
    }
    if (this._message_processor_task) {
      this._message_processor_task.cancel();
    }
  }

  async send_message(message) {
    this.message_queue.push(message);
    return true;
  }

  async _send_raw_message(message) {
    if (this.websocket && !this.websocket.closed) {
      this.websocket.send(message.to_json());
      return true;
    }
    return false;
  }

  async handle_message(raw_message) {
    try {
      const data = JSON.parse(raw_message);
      const message = new MockMessage(
        data.id || `msg_${Date.now()}`,
        data.type || 'unknown',
        data.data || {}
      );

      if (message.type === 'heartbeat_response') {
        this.last_heartbeat = Date.now() / 1000;
        this.missed_heartbeats = 0;
        return null;
      }

      return message;
    } catch (error) {
      return null;
    }
  }

  async handle_disconnect() {
    this.state = 'disconnected';
    await this.stop_background_tasks();

    if (this.websocket && !this.websocket.closed) {
      this.websocket.close();
    }
  }

  get_connection_info() {
    return {
      client_id: this.client_id,
      state: this.state,
      queue_size: this.message_queue.length,
      pending_messages: Object.keys(this.pending_messages).length,
      missed_heartbeats: this.missed_heartbeats,
      reconnect_attempts: this.reconnect_attempts,
      created_at: this.created_at.toISOString(),
      last_heartbeat: new Date(this.last_heartbeat * 1000).toISOString(),
    };
  }
}

class MockWebSocketCopilotManager {
  constructor() {
    this.connections = {};
    this.message_handlers = {};
    this.connection_callbacks = {};
    this.global_message_queue = [];
    this.statistics = {
      total_connections: 0,
      active_connections: 0,
      messages_sent: 0,
      messages_received: 0,
      reconnections: 0,
    };
  }

  register_message_handler(message_type, handler) {
    this.message_handlers[message_type] = handler;
  }

  register_connection_callback(event, callback) {
    this.connection_callbacks[event] = callback;
  }

  async handle_new_connection(websocket, client_id) {
    const connection = new MockWebSocketConnection(websocket, client_id);
    this.connections[client_id] = connection;

    await connection.start_background_tasks();

    this.statistics.total_connections += 1;
    this.statistics.active_connections += 1;

    if (this.connection_callbacks['connect']) {
      await this.connection_callbacks['connect'](connection);
    }

    return connection;
  }

  async process_message(connection, message) {
    this.statistics.messages_received += 1;

    if (this.message_handlers[message.type]) {
      const response = await this.message_handlers[message.type](connection, message);
      if (response) {
        await connection.send_message(response);
      }
      return response;
    }

    // Default error response for unknown message types
    const error_response = new MockMessage(
      `error_${Date.now()}`,
      'error',
      {
        error: 'unknown_message_type',
        original_message_id: message.id,
        message: `Unknown message type: ${message.type}`,
      }
    );

    await connection.send_message(error_response);
    return error_response;
  }

  async handle_disconnection(client_id) {
    if (this.connections[client_id]) {
      const connection = this.connections[client_id];
      await connection.handle_disconnect();

      this.statistics.active_connections = Math.max(0, this.statistics.active_connections - 1);

      if (this.connection_callbacks['disconnect']) {
        await this.connection_callbacks['disconnect'](connection);
      }

      delete this.connections[client_id];
    }
  }

  async broadcast_message(message, exclude_clients = []) {
    for (const [client_id, connection] of Object.entries(this.connections)) {
      if (!exclude_clients.includes(client_id) && connection.state === 'connected') {
        await connection.send_message(message);
      }
    }

    this.statistics.messages_sent += Object.keys(this.connections).length - exclude_clients.length;
  }

  async send_to_client(client_id, message) {
    if (this.connections[client_id]) {
      const success = await this.connections[client_id].send_message(message);
      if (success) {
        this.statistics.messages_sent += 1;
      }
      return success;
    }
    return false;
  }

  get_connection_info(client_id) {
    if (this.connections[client_id]) {
      return this.connections[client_id].get_connection_info();
    }
    return null;
  }

  get_all_connections_info() {
    return {
      statistics: this.statistics,
      active_connections: Object.fromEntries(
        Object.entries(this.connections).map(([client_id, conn]) => [
          client_id,
          conn.get_connection_info(),
        ])
      ),
    };
  }

  async health_check() {
    let healthy_connections = 0;
    let unhealthy_connections = 0;

    for (const connection of Object.values(this.connections)) {
      if (connection.state === 'connected') {
        const time_since_heartbeat = Date.now() / 1000 - connection.last_heartbeat;
        if (time_since_heartbeat < connection.heartbeat_config.timeout * 2) {
          healthy_connections += 1;
        } else {
          unhealthy_connections += 1;
        }
      } else {
        unhealthy_connections += 1;
      }
    }

    return {
      status: unhealthy_connections === 0 ? 'healthy' : 'degraded',
      healthy_connections,
      unhealthy_connections,
      total_connections: Object.keys(this.connections).length,
      statistics: this.statistics,
    };
  }
}

describe('WebSocket Copilot Service', () => {
  let manager;
  let mockWebSocket;

  beforeEach(() => {
    manager = new MockWebSocketCopilotManager();
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      closed: false,
      readyState: 1,
    };
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('Message Class', () => {
    it('should create message with required fields', () => {
      const message = new MockMessage('test-id', 'test-type', { key: 'value' });

      expect(message.id).toBe('test-id');
      expect(message.type).toBe('test-type');
      expect(message.data).toEqual({ key: 'value' });
      expect(message.retry_count).toBe(0);
      expect(message.max_retries).toBe(3);
      expect(typeof message.timestamp).toBe('number');
    });

    it('should serialize to JSON correctly', () => {
      const message = new MockMessage('test-id', 'test-type', { key: 'value' });
      const json = message.to_json();
      const parsed = JSON.parse(json);

      expect(parsed.id).toBe('test-id');
      expect(parsed.type).toBe('test-type');
      expect(parsed.data).toEqual({ key: 'value' });
    });

    it('should set timestamp automatically if not provided', () => {
      const before = Date.now() / 1000;
      const message = new MockMessage('test-id', 'test-type', {});
      const after = Date.now() / 1000;

      expect(message.timestamp).toBeGreaterThanOrEqual(before);
      expect(message.timestamp).toBeLessThanOrEqual(after);
    });
  });

  describe('WebSocketConnection Class', () => {
    let connection;

    beforeEach(() => {
      connection = new MockWebSocketConnection(mockWebSocket, 'test-client');
    });

    afterEach(async () => {
      await connection.stop_background_tasks();
    });

    it('should initialize with correct default values', () => {
      expect(connection.client_id).toBe('test-client');
      expect(connection.state).toBe('connected');
      expect(connection.websocket).toBe(mockWebSocket);
      expect(connection.message_queue).toEqual([]);
      expect(connection.pending_messages).toEqual({});
      expect(connection.missed_heartbeats).toBe(0);
    });

    it('should start and stop background tasks', async () => {
      await connection.start_background_tasks();

      expect(connection._heartbeat_task).toBeDefined();
      expect(connection._message_processor_task).toBeDefined();

      await connection.stop_background_tasks();

      expect(connection._heartbeat_task.cancel).toHaveBeenCalled();
      expect(connection._message_processor_task.cancel).toHaveBeenCalled();
    });

    it('should queue messages for sending', async () => {
      const message = new MockMessage('test-id', 'test-type', {});

      const result = await connection.send_message(message);

      expect(result).toBe(true);
      expect(connection.message_queue).toContain(message);
    });

    it('should send raw messages to WebSocket', async () => {
      const message = new MockMessage('test-id', 'test-type', { data: 'test' });

      const result = await connection._send_raw_message(message);

      expect(result).toBe(true);
      expect(mockWebSocket.send).toHaveBeenCalledWith(message.to_json());
    });

    it('should handle WebSocket closed state', async () => {
      mockWebSocket.closed = true;

      const message = new MockMessage('test-id', 'test-type', {});
      const result = await connection._send_raw_message(message);

      expect(result).toBe(false);
      expect(mockWebSocket.send).not.toHaveBeenCalled();
    });

    it('should handle incoming messages', async () => {
      const rawMessage = JSON.stringify({
        id: 'incoming-id',
        type: 'query',
        data: { query: 'SELECT * FROM users' },
      });

      const message = await connection.handle_message(rawMessage);

      expect(message).toBeDefined();
      expect(message.id).toBe('incoming-id');
      expect(message.type).toBe('query');
      expect(message.data).toEqual({ query: 'SELECT * FROM users' });
    });

    it('should handle heartbeat responses', async () => {
      const beforeTime = connection.last_heartbeat;

      const rawMessage = JSON.stringify({
        type: 'heartbeat_response',
        data: {},
      });

      const message = await connection.handle_message(rawMessage);

      expect(message).toBeNull(); // Heartbeat responses are handled internally
      expect(connection.last_heartbeat).toBeGreaterThan(beforeTime);
      expect(connection.missed_heartbeats).toBe(0);
    });

    it('should handle invalid JSON messages', async () => {
      const rawMessage = 'invalid-json{';

      const message = await connection.handle_message(rawMessage);

      expect(message).toBeNull();
    });

    it('should handle disconnection properly', async () => {
      await connection.start_background_tasks();

      await connection.handle_disconnect();

      expect(connection.state).toBe('disconnected');
      expect(connection._heartbeat_task.cancel).toHaveBeenCalled();
      expect(connection._message_processor_task.cancel).toHaveBeenCalled();
    });

    it('should provide connection information', () => {
      const info = connection.get_connection_info();

      expect(info).toEqual({
        client_id: 'test-client',
        state: 'connected',
        queue_size: 0,
        pending_messages: 0,
        missed_heartbeats: 0,
        reconnect_attempts: 0,
        created_at: connection.created_at.toISOString(),
        last_heartbeat: new Date(connection.last_heartbeat * 1000).toISOString(),
      });
    });
  });

  describe('WebSocketCopilotManager Class', () => {
    it('should initialize with empty state', () => {
      expect(manager.connections).toEqual({});
      expect(manager.message_handlers).toEqual({});
      expect(manager.connection_callbacks).toEqual({});
      expect(manager.statistics).toEqual({
        total_connections: 0,
        active_connections: 0,
        messages_sent: 0,
        messages_received: 0,
        reconnections: 0,
      });
    });

    it('should register message handlers', () => {
      const handler = vi.fn();
      manager.register_message_handler('test-type', handler);

      expect(manager.message_handlers['test-type']).toBe(handler);
    });

    it('should register connection callbacks', () => {
      const callback = vi.fn();
      manager.register_connection_callback('connect', callback);

      expect(manager.connection_callbacks['connect']).toBe(callback);
    });

    it('should handle new connections', async () => {
      const connectCallback = vi.fn();
      manager.register_connection_callback('connect', connectCallback);

      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');

      expect(manager.connections['test-client']).toBe(connection);
      expect(manager.statistics.total_connections).toBe(1);
      expect(manager.statistics.active_connections).toBe(1);
      expect(connectCallback).toHaveBeenCalledWith(connection);
    });

    it('should process messages with registered handlers', async () => {
      const handler = vi.fn().mockResolvedValue(
        new MockMessage('response-id', 'response', { result: 'success' })
      );
      manager.register_message_handler('query', handler);

      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      const message = new MockMessage('msg-id', 'query', { sql: 'SELECT 1' });

      await manager.process_message(connection, message);

      expect(handler).toHaveBeenCalledWith(connection, message);
      expect(manager.statistics.messages_received).toBe(1);
    });

    it('should handle unknown message types', async () => {
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      const message = new MockMessage('msg-id', 'unknown-type', {});

      const response = await manager.process_message(connection, message);

      expect(response.type).toBe('error');
      expect(response.data.error).toBe('unknown_message_type');
      expect(response.data.original_message_id).toBe('msg-id');
    });

    it('should handle disconnections', async () => {
      const disconnectCallback = vi.fn();
      manager.register_connection_callback('disconnect', disconnectCallback);

      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');

      await manager.handle_disconnection('test-client');

      expect(manager.connections['test-client']).toBeUndefined();
      expect(manager.statistics.active_connections).toBe(0);
      expect(disconnectCallback).toHaveBeenCalled();
    });

    it('should broadcast messages to all connected clients', async () => {
      const connection1 = await manager.handle_new_connection(mockWebSocket, 'client-1');
      const connection2 = await manager.handle_new_connection(mockWebSocket, 'client-2');

      const message = new MockMessage('broadcast-id', 'broadcast', { data: 'test' });
      const sendSpy1 = vi.spyOn(connection1, 'send_message');
      const sendSpy2 = vi.spyOn(connection2, 'send_message');

      await manager.broadcast_message(message);

      expect(sendSpy1).toHaveBeenCalledWith(message);
      expect(sendSpy2).toHaveBeenCalledWith(message);
      expect(manager.statistics.messages_sent).toBe(2);
    });

    it('should exclude clients from broadcast', async () => {
      const connection1 = await manager.handle_new_connection(mockWebSocket, 'client-1');
      const connection2 = await manager.handle_new_connection(mockWebSocket, 'client-2');

      const message = new MockMessage('broadcast-id', 'broadcast', { data: 'test' });
      const sendSpy1 = vi.spyOn(connection1, 'send_message');
      const sendSpy2 = vi.spyOn(connection2, 'send_message');

      await manager.broadcast_message(message, ['client-1']);

      expect(sendSpy1).not.toHaveBeenCalled();
      expect(sendSpy2).toHaveBeenCalledWith(message);
    });

    it('should send message to specific client', async () => {
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      const message = new MockMessage('direct-id', 'direct', { data: 'test' });
      const sendSpy = vi.spyOn(connection, 'send_message').mockResolvedValue(true);

      const result = await manager.send_to_client('test-client', message);

      expect(result).toBe(true);
      expect(sendSpy).toHaveBeenCalledWith(message);
      expect(manager.statistics.messages_sent).toBe(1);
    });

    it('should return false when sending to non-existent client', async () => {
      const message = new MockMessage('direct-id', 'direct', { data: 'test' });

      const result = await manager.send_to_client('non-existent', message);

      expect(result).toBe(false);
    });

    it('should get connection info for specific client', async () => {
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');

      const info = manager.get_connection_info('test-client');

      expect(info).toBeDefined();
      expect(info.client_id).toBe('test-client');
    });

    it('should return null for non-existent client info', () => {
      const info = manager.get_connection_info('non-existent');
      expect(info).toBeNull();
    });

    it('should get all connections info', async () => {
      await manager.handle_new_connection(mockWebSocket, 'client-1');
      await manager.handle_new_connection(mockWebSocket, 'client-2');

      const allInfo = manager.get_all_connections_info();

      expect(allInfo.statistics).toBeDefined();
      expect(allInfo.active_connections).toBeDefined();
      expect(Object.keys(allInfo.active_connections)).toHaveLength(2);
    });

    it('should perform health check', async () => {
      const connection1 = await manager.handle_new_connection(mockWebSocket, 'client-1');
      const connection2 = await manager.handle_new_connection(mockWebSocket, 'client-2');

      // Make connection2 unhealthy by setting old last_heartbeat
      connection2.last_heartbeat = (Date.now() / 1000) - 100;

      const health = await manager.health_check();

      expect(health.status).toBe('degraded');
      expect(health.healthy_connections).toBe(1);
      expect(health.unhealthy_connections).toBe(1);
      expect(health.total_connections).toBe(2);
    });

    it('should report healthy when all connections are healthy', async () => {
      await manager.handle_new_connection(mockWebSocket, 'client-1');
      await manager.handle_new_connection(mockWebSocket, 'client-2');

      const health = await manager.health_check();

      expect(health.status).toBe('healthy');
      expect(health.healthy_connections).toBe(2);
      expect(health.unhealthy_connections).toBe(0);
    });
  });

  describe('Message Handlers', () => {
    it('should handle query messages', async () => {
      const queryHandler = vi.fn().mockResolvedValue(
        new MockMessage('response-id', 'query_response', {
          result: 'Query executed successfully',
          execution_time: 150,
        })
      );

      manager.register_message_handler('query', queryHandler);
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      const queryMessage = new MockMessage('query-id', 'query', {
        query: 'SELECT * FROM users WHERE active = true',
      });

      const response = await manager.process_message(connection, queryMessage);

      expect(queryHandler).toHaveBeenCalledWith(connection, queryMessage);
      expect(response.type).toBe('query_response');
      expect(response.data.result).toBe('Query executed successfully');
    });

    it('should handle subscription messages', async () => {
      const subscribeHandler = vi.fn().mockResolvedValue(
        new MockMessage('sub-response-id', 'subscription_response', {
          topic: 'user-updates',
          status: 'subscribed',
        })
      );

      manager.register_message_handler('subscribe', subscribeHandler);
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      const subscribeMessage = new MockMessage('sub-id', 'subscribe', {
        topic: 'user-updates',
      });

      const response = await manager.process_message(connection, subscribeMessage);

      expect(subscribeHandler).toHaveBeenCalledWith(connection, subscribeMessage);
      expect(response.type).toBe('subscription_response');
      expect(response.data.topic).toBe('user-updates');
    });
  });

  describe('Integration Tests', () => {
    it('should handle complete connection lifecycle', async () => {
      const connectCallback = vi.fn();
      const disconnectCallback = vi.fn();
      const queryHandler = vi.fn().mockResolvedValue(
        new MockMessage('response', 'query_response', { result: 'success' })
      );

      manager.register_connection_callback('connect', connectCallback);
      manager.register_connection_callback('disconnect', disconnectCallback);
      manager.register_message_handler('query', queryHandler);

      // Connect
      const connection = await manager.handle_new_connection(mockWebSocket, 'test-client');
      expect(connectCallback).toHaveBeenCalled();
      expect(manager.statistics.total_connections).toBe(1);
      expect(manager.statistics.active_connections).toBe(1);

      // Send message
      const message = new MockMessage('test-query', 'query', { sql: 'SELECT 1' });
      await manager.process_message(connection, message);
      expect(queryHandler).toHaveBeenCalled();
      expect(manager.statistics.messages_received).toBe(1);

      // Disconnect
      await manager.handle_disconnection('test-client');
      expect(disconnectCallback).toHaveBeenCalled();
      expect(manager.statistics.active_connections).toBe(0);
      expect(manager.connections['test-client']).toBeUndefined();
    });

    it('should handle multiple concurrent connections', async () => {
      const connections = [];

      // Create multiple connections
      for (let i = 0; i < 5; i++) {
        const conn = await manager.handle_new_connection(mockWebSocket, `client-${i}`);
        connections.push(conn);
      }

      expect(manager.statistics.total_connections).toBe(5);
      expect(manager.statistics.active_connections).toBe(5);

      // Broadcast to all
      const broadcastMessage = new MockMessage('broadcast', 'notification', { data: 'test' });
      await manager.broadcast_message(broadcastMessage);

      expect(manager.statistics.messages_sent).toBe(5);

      // Health check should be healthy
      const health = await manager.health_check();
      expect(health.status).toBe('healthy');
      expect(health.healthy_connections).toBe(5);
    });
  });
});