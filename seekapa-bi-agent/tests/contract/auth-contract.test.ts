import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { InteractionObject } from '@pact-foundation/pact';
import { mockProvider, API_BASE_URL, Matchers, commonHeaders, createAPIResponse, createAPIError } from './pact-setup';

describe('Authentication API Contract Tests', () => {
  beforeAll(async () => {
    await mockProvider.setup();
  });

  afterAll(async () => {
    await mockProvider.finalize();
  });

  beforeEach(async () => {
    await mockProvider.removeInteractions();
  });

  describe('POST /api/auth/login', () => {
    it('should authenticate user with valid credentials', async () => {
      const loginRequest = {
        email: 'test@example.com',
        password: 'testpassword'
      };

      const expectedResponse = createAPIResponse({
        access_token: Matchers.string('eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'),
        token_type: 'bearer',
        expires_in: 3600,
        user: {
          id: Matchers.uuid(),
          email: Matchers.email(),
          username: Matchers.string('testuser'),
          is_active: Matchers.boolean(),
          created_at: Matchers.iso8601DateTime(),
          last_login: Matchers.iso8601DateTime()
        }
      });

      const interaction: InteractionObject = {
        state: 'user exists with valid credentials',
        uponReceiving: 'a login request with valid credentials',
        withRequest: {
          method: 'POST',
          path: '/api/auth/login',
          headers: commonHeaders,
          body: loginRequest
        },
        willRespondWith: {
          status: 200,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      // Make the actual request
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(loginRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.access_token).toBeDefined();
      expect(data.data.user.email).toBe('test@example.com');

      await mockProvider.verify();
    });

    it('should reject authentication with invalid credentials', async () => {
      const invalidLoginRequest = {
        email: 'invalid@example.com',
        password: 'wrongpassword'
      };

      const expectedResponse = createAPIError(401, 'Invalid credentials', 'Email or password is incorrect');

      const interaction: InteractionObject = {
        state: 'user does not exist or credentials are invalid',
        uponReceiving: 'a login request with invalid credentials',
        withRequest: {
          method: 'POST',
          path: '/api/auth/login',
          headers: commonHeaders,
          body: invalidLoginRequest
        },
        willRespondWith: {
          status: 401,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(invalidLoginRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(401);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(401);
      expect(data.error.message).toBe('Invalid credentials');

      await mockProvider.verify();
    });

    it('should validate required fields in login request', async () => {
      const incompleteRequest = {
        email: 'test@example.com'
        // Missing password
      };

      const expectedResponse = createAPIError(400, 'Validation error', 'Password is required');

      const interaction: InteractionObject = {
        uponReceiving: 'a login request with missing password',
        withRequest: {
          method: 'POST',
          path: '/api/auth/login',
          headers: commonHeaders,
          body: incompleteRequest
        },
        willRespondWith: {
          status: 400,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(incompleteRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(400);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(400);

      await mockProvider.verify();
    });
  });

  describe('POST /api/auth/register', () => {
    it('should register new user successfully', async () => {
      const registerRequest = {
        username: 'newuser',
        email: 'newuser@example.com',
        password: 'newpassword123'
      };

      const expectedResponse = createAPIResponse({
        user: {
          id: Matchers.uuid(),
          username: Matchers.string('newuser'),
          email: Matchers.email(),
          is_active: Matchers.boolean(),
          created_at: Matchers.iso8601DateTime()
        },
        message: 'User registered successfully'
      });

      const interaction: InteractionObject = {
        state: 'user does not exist',
        uponReceiving: 'a registration request with valid data',
        withRequest: {
          method: 'POST',
          path: '/api/auth/register',
          headers: commonHeaders,
          body: registerRequest
        },
        willRespondWith: {
          status: 201,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(registerRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(201);
      expect(data.success).toBe(true);
      expect(data.data.user.username).toBe('newuser');
      expect(data.data.user.email).toBe('newuser@example.com');

      await mockProvider.verify();
    });

    it('should reject registration with existing email', async () => {
      const existingUserRequest = {
        username: 'differentuser',
        email: 'existing@example.com',
        password: 'password123'
      };

      const expectedResponse = createAPIError(409, 'User already exists', 'Email is already registered');

      const interaction: InteractionObject = {
        state: 'user with email already exists',
        uponReceiving: 'a registration request with existing email',
        withRequest: {
          method: 'POST',
          path: '/api/auth/register',
          headers: commonHeaders,
          body: existingUserRequest
        },
        willRespondWith: {
          status: 409,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(existingUserRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(409);
      expect(data.success).toBe(false);
      expect(data.error.code).toBe(409);

      await mockProvider.verify();
    });
  });

  describe('POST /api/auth/refresh', () => {
    it('should refresh access token with valid refresh token', async () => {
      const refreshRequest = {
        refresh_token: 'valid_refresh_token'
      };

      const expectedResponse = createAPIResponse({
        access_token: Matchers.string('new_access_token'),
        token_type: 'bearer',
        expires_in: 3600
      });

      const interaction: InteractionObject = {
        state: 'valid refresh token exists',
        uponReceiving: 'a token refresh request',
        withRequest: {
          method: 'POST',
          path: '/api/auth/refresh',
          headers: commonHeaders,
          body: refreshRequest
        },
        willRespondWith: {
          status: 200,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(refreshRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.data.access_token).toBeDefined();

      await mockProvider.verify();
    });

    it('should reject refresh with invalid token', async () => {
      const invalidRefreshRequest = {
        refresh_token: 'invalid_refresh_token'
      };

      const expectedResponse = createAPIError(401, 'Invalid refresh token');

      const interaction: InteractionObject = {
        state: 'refresh token is invalid',
        uponReceiving: 'a token refresh request with invalid token',
        withRequest: {
          method: 'POST',
          path: '/api/auth/refresh',
          headers: commonHeaders,
          body: invalidRefreshRequest
        },
        willRespondWith: {
          status: 401,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: commonHeaders,
        body: JSON.stringify(invalidRefreshRequest)
      });

      const data = await response.json();

      expect(response.status).toBe(401);
      expect(data.success).toBe(false);

      await mockProvider.verify();
    });
  });

  describe('POST /api/auth/logout', () => {
    it('should logout user successfully', async () => {
      const expectedResponse = createAPIResponse({
        message: 'Logged out successfully'
      });

      const interaction: InteractionObject = {
        state: 'user is authenticated',
        uponReceiving: 'a logout request',
        withRequest: {
          method: 'POST',
          path: '/api/auth/logout',
          headers: {
            ...commonHeaders,
            'Authorization': 'Bearer valid_token'
          }
        },
        willRespondWith: {
          status: 200,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: {
          ...commonHeaders,
          'Authorization': 'Bearer valid_token'
        }
      });

      const data = await response.json();

      expect(response.status).toBe(200);
      expect(data.success).toBe(true);

      await mockProvider.verify();
    });

    it('should reject logout without authentication', async () => {
      const expectedResponse = createAPIError(401, 'Unauthorized', 'Authentication required');

      const interaction: InteractionObject = {
        uponReceiving: 'a logout request without authentication',
        withRequest: {
          method: 'POST',
          path: '/api/auth/logout',
          headers: commonHeaders
        },
        willRespondWith: {
          status: 401,
          headers: commonHeaders,
          body: expectedResponse
        }
      };

      await mockProvider.addInteraction(interaction);

      const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: commonHeaders
      });

      const data = await response.json();

      expect(response.status).toBe(401);
      expect(data.success).toBe(false);

      await mockProvider.verify();
    });
  });
});