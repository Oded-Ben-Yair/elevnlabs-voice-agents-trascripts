import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import {
  createMockUser,
  createMockQuery,
  createMockReport,
  createMockAPIResponse,
  createMockAPIError,
  resetTestDatabase,
  seedTestDatabase
} from '../fixtures/test-data';

// Mock fetch for API calls
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Test configuration
const API_BASE_URL = 'http://localhost:8000/api';
const TEST_TIMEOUT = 30000;

// Helper function to make API requests
const apiRequest = async (endpoint: string, options: RequestInit = {}) => {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  const data = await response.json();
  return { response, data };
};

// Helper function to authenticate and get token
const authenticate = async (email: string = 'test@example.com', password: string = 'testpassword') => {
  const { response, data } = await apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });

  if (response.ok && data.access_token) {
    return data.access_token;
  }

  throw new Error(`Authentication failed: ${data.message}`);
};

// Helper function to make authenticated requests
const authenticatedRequest = async (endpoint: string, token: string, options: RequestInit = {}) => {
  return apiRequest(endpoint, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
    },
  });
};

describe('API Integration Tests', () => {
  let authToken: string;
  let testUser: any;

  beforeAll(async () => {
    // Setup test database
    await resetTestDatabase();
    await seedTestDatabase();

    testUser = createMockUser({
      email: 'test@example.com',
      username: 'testuser',
    });
  }, TEST_TIMEOUT);

  afterAll(async () => {
    // Cleanup test database
    await resetTestDatabase();
  }, TEST_TIMEOUT);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('Authentication Flow', () => {
    it('should register a new user', async () => {
      const newUser = createMockUser({
        email: 'newuser@example.com',
        username: 'newuser',
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => createMockAPIResponse({
          user: {
            id: newUser.id,
            email: newUser.email,
            username: newUser.username,
          },
          message: 'User registered successfully'
        })
      });

      const { response, data } = await apiRequest('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email: newUser.email,
          username: newUser.username,
          password: 'password123'
        }),
      });

      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
      expect(data.data.user.email).toBe(newUser.email);
      expect(mockFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/auth/register`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({
            email: newUser.email,
            username: newUser.username,
            password: 'password123'
          }),
        })
      );
    });

    it('should login with valid credentials', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'mock-jwt-token',
          token_type: 'bearer',
          expires_in: 3600,
          user: testUser
        })
      });

      authToken = await authenticate();

      expect(authToken).toBe('mock-jwt-token');
      expect(mockFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/auth/login`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            email: 'test@example.com',
            password: 'testpassword'
          }),
        })
      );
    });

    it('should fail login with invalid credentials', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => createMockAPIError({
          error: {
            code: 401,
            message: 'Invalid credentials',
            details: 'Email or password is incorrect'
          }
        })
      });

      await expect(authenticate('invalid@example.com', 'wrongpassword')).rejects.toThrow('Authentication failed');
    });

    it('should refresh authentication token', async () => {
      const refreshToken = 'mock-refresh-token';

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'new-mock-jwt-token',
          token_type: 'bearer',
          expires_in: 3600
        })
      });

      const { response, data } = await apiRequest('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      expect(response.ok).toBe(true);
      expect(data.data.access_token).toBe('new-mock-jwt-token');
    });

    it('should logout successfully', async () => {
      const token = 'mock-jwt-token';

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          message: 'Logged out successfully'
        })
      });

      const { response, data } = await authenticatedRequest('/auth/logout', token, {
        method: 'POST',
      });

      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
    });
  });

  describe('Query Management', () => {
    beforeEach(async () => {
      // Mock authentication for query tests
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'mock-jwt-token',
          user: testUser
        })
      });
      authToken = await authenticate();
    });

    it('should create a new query', async () => {
      const queryData = {
        query_text: 'SELECT * FROM users WHERE active = true',
        params: {
          filters: { active: true },
          limit: 100
        }
      };

      const mockQuery = createMockQuery({
        userId: testUser.id,
        queryText: queryData.query_text,
        params: queryData.params
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => createMockAPIResponse(mockQuery)
      });

      const { response, data } = await authenticatedRequest('/queries', authToken, {
        method: 'POST',
        body: JSON.stringify(queryData),
      });

      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
      expect(data.data.queryText).toBe(queryData.query_text);
      expect(data.data.params).toEqual(queryData.params);
    });

    it('should execute a query', async () => {
      const queryId = 'test-query-id';
      const mockResults = {
        columns: ['id', 'name', 'email'],
        rows: [
          [1, 'John Doe', 'john@example.com'],
          [2, 'Jane Smith', 'jane@example.com']
        ],
        total_count: 2,
        execution_time: 150
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockResults)
      });

      const { response, data } = await authenticatedRequest(`/queries/${queryId}/execute`, authToken, {
        method: 'POST',
      });

      expect(response.ok).toBe(true);
      expect(data.data.columns).toEqual(['id', 'name', 'email']);
      expect(data.data.rows).toHaveLength(2);
      expect(data.data.execution_time).toBe(150);
    });

    it('should get user queries with pagination', async () => {
      const mockQueries = Array.from({ length: 5 }, () =>
        createMockQuery({ userId: testUser.id })
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          queries: mockQueries,
          pagination: {
            page: 1,
            limit: 10,
            total: 5,
            total_pages: 1
          }
        })
      });

      const { response, data } = await authenticatedRequest('/queries?page=1&limit=10', authToken);

      expect(response.ok).toBe(true);
      expect(data.data.queries).toHaveLength(5);
      expect(data.data.pagination.total).toBe(5);
    });

    it('should get query by id', async () => {
      const queryId = 'test-query-id';
      const mockQuery = createMockQuery({ id: queryId, userId: testUser.id });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockQuery)
      });

      const { response, data } = await authenticatedRequest(`/queries/${queryId}`, authToken);

      expect(response.ok).toBe(true);
      expect(data.data.id).toBe(queryId);
      expect(data.data.userId).toBe(testUser.id);
    });

    it('should update a query', async () => {
      const queryId = 'test-query-id';
      const updateData = {
        query_text: 'SELECT * FROM users WHERE created_at > ?',
        params: { date_filter: '2024-01-01' }
      };

      const updatedQuery = createMockQuery({
        id: queryId,
        userId: testUser.id,
        queryText: updateData.query_text,
        params: updateData.params
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(updatedQuery)
      });

      const { response, data } = await authenticatedRequest(`/queries/${queryId}`, authToken, {
        method: 'PUT',
        body: JSON.stringify(updateData),
      });

      expect(response.ok).toBe(true);
      expect(data.data.queryText).toBe(updateData.query_text);
      expect(data.data.params).toEqual(updateData.params);
    });

    it('should delete a query', async () => {
      const queryId = 'test-query-id';

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          message: 'Query deleted successfully'
        })
      });

      const { response, data } = await authenticatedRequest(`/queries/${queryId}`, authToken, {
        method: 'DELETE',
      });

      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
    });
  });

  describe('Report Management', () => {
    beforeEach(async () => {
      // Mock authentication for report tests
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'mock-jwt-token',
          user: testUser
        })
      });
      authToken = await authenticate();
    });

    it('should create a new report', async () => {
      const reportData = {
        title: 'Sales Dashboard',
        description: 'Monthly sales performance report',
        data: {
          charts: [
            { type: 'bar', data: [1, 2, 3, 4, 5] },
            { type: 'line', data: [10, 20, 15, 25, 30] }
          ]
        }
      };

      const mockReport = createMockReport({
        userId: testUser.id,
        title: reportData.title,
        description: reportData.description,
        data: reportData.data
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => createMockAPIResponse(mockReport)
      });

      const { response, data } = await authenticatedRequest('/reports', authToken, {
        method: 'POST',
        body: JSON.stringify(reportData),
      });

      expect(response.ok).toBe(true);
      expect(data.data.title).toBe(reportData.title);
      expect(data.data.data.charts).toHaveLength(2);
    });

    it('should get user reports', async () => {
      const mockReports = Array.from({ length: 3 }, () =>
        createMockReport({ userId: testUser.id })
      );

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          reports: mockReports,
          pagination: {
            page: 1,
            limit: 10,
            total: 3,
            total_pages: 1
          }
        })
      });

      const { response, data } = await authenticatedRequest('/reports', authToken);

      expect(response.ok).toBe(true);
      expect(data.data.reports).toHaveLength(3);
    });

    it('should export report as PDF', async () => {
      const reportId = 'test-report-id';
      const mockPdfBuffer = Buffer.from('fake-pdf-content');

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'application/pdf',
          'Content-Disposition': 'attachment; filename="report.pdf"'
        }),
        arrayBuffer: async () => mockPdfBuffer.buffer
      });

      const response = await fetch(`${API_BASE_URL}/reports/${reportId}/export?format=pdf`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
        },
      });

      expect(response.ok).toBe(true);
      expect(response.headers.get('Content-Type')).toBe('application/pdf');
    });
  });

  describe('PowerBI Integration', () => {
    beforeEach(async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'mock-jwt-token',
          user: testUser
        })
      });
      authToken = await authenticate();
    });

    it('should authenticate with PowerBI', async () => {
      const mockAuthResponse = {
        access_token: 'powerbi-access-token',
        refresh_token: 'powerbi-refresh-token',
        expires_in: 3600
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockAuthResponse)
      });

      const { response, data } = await authenticatedRequest('/powerbi/auth', authToken, {
        method: 'POST',
        body: JSON.stringify({
          client_id: 'powerbi-client-id',
          client_secret: 'powerbi-client-secret'
        }),
      });

      expect(response.ok).toBe(true);
      expect(data.data.access_token).toBe('powerbi-access-token');
    });

    it('should get PowerBI reports', async () => {
      const mockReports = [
        {
          id: 'report-1',
          name: 'Sales Dashboard',
          datasetId: 'dataset-1',
          webUrl: 'https://app.powerbi.com/reports/report-1'
        },
        {
          id: 'report-2',
          name: 'Marketing Analytics',
          datasetId: 'dataset-2',
          webUrl: 'https://app.powerbi.com/reports/report-2'
        }
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          reports: mockReports
        })
      });

      const { response, data } = await authenticatedRequest('/powerbi/reports', authToken);

      expect(response.ok).toBe(true);
      expect(data.data.reports).toHaveLength(2);
    });

    it('should get PowerBI embed token', async () => {
      const reportId = 'test-report-id';
      const mockEmbedToken = {
        token: 'embed-token-123',
        tokenId: 'token-id-123',
        expiration: '2024-12-31T23:59:59Z'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockEmbedToken)
      });

      const { response, data } = await authenticatedRequest(`/powerbi/reports/${reportId}/embed-token`, authToken);

      expect(response.ok).toBe(true);
      expect(data.data.token).toBe('embed-token-123');
    });
  });

  describe('Analytics and Insights', () => {
    beforeEach(async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          access_token: 'mock-jwt-token',
          user: testUser
        })
      });
      authToken = await authenticate();
    });

    it('should get user analytics dashboard', async () => {
      const mockAnalytics = {
        total_queries: 150,
        avg_execution_time: 2.5,
        success_rate: 0.98,
        most_used_tables: ['users', 'orders', 'products'],
        query_trends: {
          daily: [10, 15, 12, 18, 20, 16, 14],
          labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        }
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockAnalytics)
      });

      const { response, data } = await authenticatedRequest('/analytics/dashboard', authToken);

      expect(response.ok).toBe(true);
      expect(data.data.total_queries).toBe(150);
      expect(data.data.query_trends.daily).toHaveLength(7);
    });

    it('should get AI insights', async () => {
      const mockInsights = [
        {
          id: 'insight-1',
          type: 'performance',
          title: 'Query Optimization Opportunity',
          description: 'Query execution time increased by 40% this week',
          confidence: 0.85,
          recommendations: ['Add index on user_id column', 'Consider query caching']
        },
        {
          id: 'insight-2',
          type: 'usage',
          title: 'Peak Usage Pattern',
          description: 'Highest query volume occurs between 9-11 AM',
          confidence: 0.92,
          recommendations: ['Consider scaling during peak hours']
        }
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse({
          insights: mockInsights
        })
      });

      const { response, data } = await authenticatedRequest('/analytics/insights', authToken);

      expect(response.ok).toBe(true);
      expect(data.data.insights).toHaveLength(2);
      expect(data.data.insights[0].type).toBe('performance');
    });
  });

  describe('Error Handling', () => {
    it('should handle 401 unauthorized errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => createMockAPIError({
          error: {
            code: 401,
            message: 'Unauthorized',
            details: 'Invalid or expired token'
          }
        })
      });

      const { response, data } = await authenticatedRequest('/queries', 'invalid-token');

      expect(response.ok).toBe(false);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(401);
    });

    it('should handle 404 not found errors', async () => {
      const queryId = 'non-existent-query';

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => createMockAPIError({
          error: {
            code: 404,
            message: 'Query not found',
            details: `Query with id ${queryId} does not exist`
          }
        })
      });

      const { response, data } = await authenticatedRequest(`/queries/${queryId}`, 'valid-token');

      expect(response.ok).toBe(false);
      expect(data.error.code).toBe(404);
    });

    it('should handle 500 server errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => createMockAPIError({
          error: {
            code: 500,
            message: 'Internal Server Error',
            details: 'Database connection failed'
          }
        })
      });

      const { response, data } = await apiRequest('/queries', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer valid-token',
        },
        body: JSON.stringify({ query_text: 'SELECT 1' }),
      });

      expect(response.ok).toBe(false);
      expect(data.error.code).toBe(500);
    });

    it('should handle network errors gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(apiRequest('/health')).rejects.toThrow('Network error');
    });
  });

  describe('Health Check and Monitoring', () => {
    it('should check API health status', async () => {
      const mockHealthStatus = {
        status: 'healthy',
        timestamp: new Date().toISOString(),
        version: '1.0.0',
        services: {
          database: 'healthy',
          redis: 'healthy',
          powerbi: 'healthy'
        },
        uptime: 3600
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockHealthStatus)
      });

      const { response, data } = await apiRequest('/health');

      expect(response.ok).toBe(true);
      expect(data.data.status).toBe('healthy');
      expect(data.data.services.database).toBe('healthy');
    });

    it('should get API metrics', async () => {
      const mockMetrics = {
        requests_per_minute: 150,
        avg_response_time: 250,
        error_rate: 0.02,
        active_connections: 45,
        database_pool_size: 10,
        cache_hit_rate: 0.85
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => createMockAPIResponse(mockMetrics)
      });

      const { response, data } = await apiRequest('/metrics');

      expect(response.ok).toBe(true);
      expect(data.data.requests_per_minute).toBe(150);
      expect(data.data.cache_hit_rate).toBe(0.85);
    });
  });

  describe('Rate Limiting', () => {
    it('should handle rate limiting errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 429,
        headers: new Headers({
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': '1640995200'
        }),
        json: async () => createMockAPIError({
          error: {
            code: 429,
            message: 'Rate limit exceeded',
            details: 'Maximum 100 requests per minute allowed'
          }
        })
      });

      const { response, data } = await authenticatedRequest('/queries', 'valid-token');

      expect(response.ok).toBe(false);
      expect(data.error.code).toBe(429);
      expect(response.headers.get('X-RateLimit-Remaining')).toBe('0');
    });
  });
});