import { Pact } from '@pact-foundation/pact';
import path from 'path';

// Pact configuration
export const mockProvider = new Pact({
  consumer: 'Seekapa-BI-Frontend',
  provider: 'Seekapa-BI-API',
  port: 1234, // Mock server port
  log: path.resolve(process.cwd(), 'logs', 'pact.log'),
  dir: path.resolve(process.cwd(), 'pacts'),
  spec: 2,
  logLevel: 'INFO',
  pactfileWriteMode: 'overwrite'
});

// Test configuration
export const API_BASE_URL = 'http://localhost:1234';

// Common matchers
export const Matchers = {
  uuid: () => ({ generate: '123e4567-e89b-12d3-a456-426614174000', matcher: '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' }),
  iso8601DateTime: () => ({ generate: '2024-01-15T10:30:00.000Z', matcher: '^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d{3})?Z$' }),
  email: () => ({ generate: 'test@example.com', matcher: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$' }),
  positiveInteger: () => ({ generate: 1, matcher: '^[1-9]\\d*$' }),
  boolean: () => ({ generate: true, matcher: '^(true|false)$' }),
  string: (example: string = 'test') => ({ generate: example, matcher: '^.+$' }),
  number: (example: number = 100) => ({ generate: example, matcher: '^\\d+(\\.\\d+)?$' }),
  array: (minLength: number = 1) => ({ generate: Array(minLength).fill({}), matcher: `^.{${minLength},}$` })
};

// Common headers
export const commonHeaders = {
  'Content-Type': 'application/json',
};

export const authHeaders = {
  ...commonHeaders,
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
};

// Helper function to create API response structure
export const createAPIResponse = (data: any, success: boolean = true) => ({
  success,
  data,
  message: success ? 'Success' : 'Error',
  timestamp: Matchers.iso8601DateTime().generate
});

// Helper function to create API error structure
export const createAPIError = (code: number, message: string, details?: string) => ({
  success: false,
  error: {
    code,
    message,
    details: details || message
  },
  timestamp: Matchers.iso8601DateTime().generate
});