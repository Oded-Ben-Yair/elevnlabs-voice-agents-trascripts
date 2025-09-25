import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { InteractionObject } from '@pact-foundation/pact';
import { mockProvider, API_BASE_URL, Matchers, authHeaders, createAPIResponse, createAPIError } from './pact-setup';

describe('Queries API Contract Tests', () => {
  beforeAll(async () => {
    await mockProvider.setup();
  });

  afterAll(async () => {
    await mockProvider.finalize();
  });

  beforeEach(async () => {
    await mockProvider.removeInteractions();
  });

  describe('POST /api/queries', () => {
    it('should create a new query successfully', async () => {
      const queryRequest = {
        query_text: 'SELECT * FROM users WHERE active = true',
        params: {
          filters: { active: true },
          limit: 100
        }
      };

      const expectedResponse = createAPIResponse({
        id: Matchers.uuid(),
        user_id: Matchers.uuid(),
        query_text: Matchers.string('SELECT * FROM users WHERE active = true'),
        params: {
          filters: { active: Matchers.boolean() },
          limit: Matchers.number(100)
        },
        execution_time: null,
        created_at: Matchers.iso8601DateTime()
      });

      const interaction: InteractionObject = {
        state: 'user is authenticated',
        uponReceiving: 'a request to create a new query',
        withRequest: {
          method: 'POST',
          path: '/api/queries',
          headers: authHeaders,
          body: queryRequest
        },
        willRespondWith: {
          status: 201,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(queryRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(201);
      expect(data.success).toBe(true);
      expect(data.data.query_text).toBe(queryRequest.query_text);
      expect(data.data.params).toEqual(queryRequest.params);

      await mockProvider.verify();
    });

    it('should reject query creation with invalid SQL', async () => {
      const invalidQueryRequest = {
        query_text: 'INVALID SQL SYNTAX',
        params: {}
      };

      const expectedResponse = createAPIError(400, 'Invalid SQL syntax', 'Query contains syntax errors');

      const interaction: InteractionObject = {
        state: 'user is authenticated',
        uponReceiving: 'a request to create a query with invalid SQL',
        withRequest: {
          method: 'POST',
          path: '/api/queries',
          headers: authHeaders,
          body: invalidQueryRequest
        },
        willRespondWith: {
          status: 400,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(invalidQueryRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(400);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(400);

      await mockProvider.verify();
    });
  });

  describe('GET /api/queries', () => {
    it('should retrieve user queries with pagination', async () => {
      const expectedResponse = createAPIResponse({
        queries: Matchers.array(3).generate.map(() => ({
          id: Matchers.uuid(),
          user_id: Matchers.uuid(),
          query_text: Matchers.string('SELECT * FROM users'),
          params: {},
          execution_time: Matchers.number(150),
          created_at: Matchers.iso8601DateTime()
        })),
        pagination: {
          page: Matchers.number(1),
          limit: Matchers.number(10),
          total: Matchers.number(25),
          total_pages: Matchers.number(3)
        }
      });

      const interaction: InteractionObject = {
        state: 'user is authenticated and has queries',
        uponReceiving: 'a request to get user queries',
        withRequest: {
          method: 'GET',
          path: '/api/queries',
          query: 'page=1&limit=10',
          headers: authHeaders
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries?page=1&limit=10`, {
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(Array.isArray(data.data.queries)).toBe(true);
      expect(data.data.pagination).toBeDefined();

      await mockProvider.verify();
    });

    it('should return empty list when user has no queries', async () => {
      const expectedResponse = createAPIResponse({
        queries: [],
        pagination: {
          page: 1,
          limit: 10,
          total: 0,
          total_pages: 0
        }
      });

      const interaction: InteractionObject = {
        state: 'user is authenticated but has no queries',
        uponReceiving: 'a request to get queries for user with no queries',
        withRequest: {
          method: 'GET',
          path: '/api/queries',
          query: 'page=1&limit=10',
          headers: authHeaders
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries?page=1&limit=10`, {
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.queries).toEqual([]);
      expect(data.data.pagination.total).toBe(0);

      await mockProvider.verify();
    });
  });

  describe('GET /api/queries/:id', () => {
    it('should retrieve specific query by ID', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIResponse({
        id: Matchers.uuid(),
        user_id: Matchers.uuid(),
        query_text: Matchers.string('SELECT COUNT(*) FROM users'),
        params: {
          filters: { active: Matchers.boolean() }
        },
        execution_time: Matchers.number(200),
        created_at: Matchers.iso8601DateTime()
      });

      const interaction: InteractionObject = {
        state: 'query exists and belongs to user',
        uponReceiving: 'a request to get a specific query',
        withRequest: {
          method: 'GET',
          path: `/api/queries/${queryId}`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}`, {
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.id).toBeDefined();

      await mockProvider.verify();
    });

    it('should return 404 for non-existent query', async () => {
      const nonExistentId = '999e4567-e89b-12d3-a456-426614174999';

      const expectedResponse = createAPIError(404, 'Query not found', `Query with id ${nonExistentId} does not exist`);

      const interaction: InteractionObject = {
        state: 'query does not exist',
        uponReceiving: 'a request to get a non-existent query',
        withRequest: {
          method: 'GET',
          path: `/api/queries/${nonExistentId}`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 404,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${nonExistentId}`, {
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(404);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(404);

      await mockProvider.verify();
    });
  });

  describe('POST /api/queries/:id/execute', () => {
    it('should execute query successfully', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIResponse({
        columns: ['id', 'name', 'email', 'created_at'],
        rows: [
          [1, 'John Doe', 'john@example.com', '2024-01-01T10:00:00Z'],
          [2, 'Jane Smith', 'jane@example.com', '2024-01-02T10:00:00Z']
        ],
        total_count: Matchers.number(2),
        execution_time: Matchers.number(150),
        executed_at: Matchers.iso8601DateTime()
      });

      const interaction: InteractionObject = {
        state: 'query exists and is executable',
        uponReceiving: 'a request to execute a query',
        withRequest: {
          method: 'POST',
          path: `/api/queries/${queryId}/execute`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}/execute`, {
        method: 'POST',
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.columns).toBeDefined();
      expect(data.data.rows).toBeDefined();
      expect(data.data.execution_time).toBeDefined();

      await mockProvider.verify();
    });

    it('should handle query execution errors', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIError(500, 'Query execution failed', 'Table "non_existent_table" does not exist');

      const interaction: InteractionObject = {
        state: 'query exists but has execution errors',
        uponReceiving: 'a request to execute a query that fails',
        withRequest: {
          method: 'POST',
          path: `/api/queries/${queryId}/execute`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 500,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}/execute`, {
        method: 'POST',
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(500);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(500);

      await mockProvider.verify();
    });

    it('should handle query timeout', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIError(408, 'Query timeout', 'Query execution exceeded maximum allowed time');

      const interaction: InteractionObject = {
        state: 'query exists but takes too long to execute',
        uponReceiving: 'a request to execute a slow query that times out',
        withRequest: {
          method: 'POST',
          path: `/api/queries/${queryId}/execute`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 408,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}/execute`, {
        method: 'POST',
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(408);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(408);

      await mockProvider.verify();
    });
  });

  describe('PUT /api/queries/:id', () => {
    it('should update query successfully', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';
      const updateRequest = {
        query_text: 'SELECT * FROM users WHERE created_at > ?',
        params: {
          date_filter: '2024-01-01'
        }
      };

      const expectedResponse = createAPIResponse({
        id: Matchers.uuid(),
        user_id: Matchers.uuid(),
        query_text: Matchers.string(updateRequest.query_text),
        params: {
          date_filter: Matchers.string('2024-01-01')
        },
        execution_time: null,
        created_at: Matchers.iso8601DateTime(),
        updated_at: Matchers.iso8601DateTime()
      });

      const interaction: InteractionObject = {
        state: 'query exists and belongs to user',
        uponReceiving: 'a request to update a query',
        withRequest: {
          method: 'PUT',
          path: `/api/queries/${queryId}`,
          headers: authHeaders,
          body: updateRequest
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify(updateRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.query_text).toBe(updateRequest.query_text);

      await mockProvider.verify();
    });
  });

  describe('DELETE /api/queries/:id', () => {
    it('should delete query successfully', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIResponse({
        message: 'Query deleted successfully'
      });

      const interaction: InteractionObject = {
        state: 'query exists and belongs to user',
        uponReceiving: 'a request to delete a query',
        withRequest: {
          method: 'DELETE',
          path: `/api/queries/${queryId}`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 200,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}`, {
        method: 'DELETE',
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);

      await mockProvider.verify();
    });

    it('should prevent deletion of query belonging to another user', async () => {
      const queryId = '123e4567-e89b-12d3-a456-426614174000';

      const expectedResponse = createAPIError(403, 'Forbidden', 'You do not have permission to delete this query');

      const interaction: InteractionObject = {
        state: 'query exists but belongs to another user',
        uponReceiving: 'a request to delete a query belonging to another user',
        withRequest: {
          method: 'DELETE',
          path: `/api/queries/${queryId}`,
          headers: authHeaders
        },
        willRespondWith: {
          status: 403,
          headers: authHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/queries/${queryId}`, {
        method: 'DELETE',
        headers: authHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(403);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(403);

      await mockProvider.verify();
    });
  });
});