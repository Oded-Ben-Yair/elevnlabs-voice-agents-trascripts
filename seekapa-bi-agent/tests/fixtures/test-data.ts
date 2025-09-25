import { faker } from '@faker-js/faker';

// User Data Factory
export const createMockUser = (overrides: Partial<User> = {}): User => ({
  id: faker.string.uuid(),
  username: faker.internet.userName(),
  email: faker.internet.email(),
  hashedPassword: faker.internet.password(),
  isActive: true,
  createdAt: faker.date.recent(),
  lastLogin: faker.date.recent(),
  ...overrides,
});

// Session Data Factory
export const createMockSession = (overrides: Partial<Session> = {}): Session => ({
  id: faker.string.uuid(),
  userId: faker.string.uuid(),
  token: faker.string.alphanumeric(64),
  expiresAt: faker.date.future(),
  createdAt: faker.date.recent(),
  isActive: true,
  ...overrides,
});

// Query Data Factory
export const createMockQuery = (overrides: Partial<Query> = {}): Query => ({
  id: faker.string.uuid(),
  userId: faker.string.uuid(),
  queryText: faker.lorem.sentence(),
  params: {
    filters: [faker.lorem.word()],
    dateRange: {
      start: faker.date.past().toISOString(),
      end: faker.date.recent().toISOString(),
    },
  },
  executionTime: faker.number.int({ min: 10, max: 5000 }),
  createdAt: faker.date.recent(),
  ...overrides,
});

// Report Data Factory
export const createMockReport = (overrides: Partial<Report> = {}): Report => ({
  id: faker.string.uuid(),
  userId: faker.string.uuid(),
  title: faker.lorem.words(3),
  description: faker.lorem.paragraph(),
  data: {
    charts: [
      {
        type: 'bar',
        data: Array.from({ length: 5 }, () => ({
          label: faker.lorem.word(),
          value: faker.number.int({ min: 1, max: 100 }),
        })),
      },
    ],
    metrics: {
      totalRecords: faker.number.int({ min: 100, max: 10000 }),
      avgResponseTime: faker.number.int({ min: 10, max: 1000 }),
    },
  },
  createdAt: faker.date.recent(),
  ...overrides,
});

// Insight Data Factory
export const createMockInsight = (overrides: Partial<Insight> = {}): Insight => ({
  id: faker.string.uuid(),
  queryId: faker.string.uuid(),
  type: faker.helpers.arrayElement(['performance', 'optimization', 'anomaly', 'trend']),
  details: {
    message: faker.lorem.sentence(),
    confidence: faker.number.float({ min: 0.5, max: 1.0 }),
    recommendations: [faker.lorem.sentence()],
    impact: faker.helpers.arrayElement(['low', 'medium', 'high']),
  },
  createdAt: faker.date.recent(),
  ...overrides,
});

// PowerBI Data Factory
export const createMockPowerBIReport = (overrides: Partial<PowerBIReport> = {}): PowerBIReport => ({
  id: faker.string.uuid(),
  name: faker.lorem.words(2),
  datasetId: faker.string.uuid(),
  embedUrl: faker.internet.url(),
  accessToken: faker.string.alphanumeric(128),
  tokenExpiry: faker.date.future(),
  createdDate: faker.date.past(),
  modifiedDate: faker.date.recent(),
  ...overrides,
});

// API Response Factories
export const createMockAPIResponse = <T>(data: T, overrides: Partial<APIResponse<T>> = {}): APIResponse<T> => ({
  success: true,
  data,
  message: 'Success',
  timestamp: new Date().toISOString(),
  ...overrides,
});

export const createMockAPIError = (overrides: Partial<APIError> = {}): APIError => ({
  success: false,
  error: {
    code: faker.number.int({ min: 400, max: 500 }),
    message: faker.lorem.sentence(),
    details: faker.lorem.paragraph(),
  },
  timestamp: new Date().toISOString(),
  ...overrides,
});

// Cache Test Data
export const createMockCacheEntry = (overrides: Partial<CacheEntry> = {}): CacheEntry => ({
  key: faker.string.alphanumeric(16),
  value: { data: faker.lorem.words() },
  ttl: faker.number.int({ min: 60, max: 3600 }),
  tags: [faker.lorem.word()],
  createdAt: faker.date.recent(),
  ...overrides,
});

// Test Scenarios
export const createTestScenarios = () => ({
  validLoginUser: createMockUser({
    email: 'test@example.com',
    username: 'testuser',
    isActive: true,
  }),

  expiredSession: createMockSession({
    expiresAt: faker.date.past(),
    isActive: false,
  }),

  complexQuery: createMockQuery({
    queryText: 'SELECT * FROM sales WHERE date BETWEEN ? AND ? AND region = ?',
    params: {
      dateStart: '2024-01-01',
      dateEnd: '2024-12-31',
      region: 'North America',
    },
    executionTime: 2500,
  }),

  performanceInsight: createMockInsight({
    type: 'performance',
    details: {
      message: 'Query execution time is above average',
      confidence: 0.85,
      recommendations: ['Add index on date column', 'Consider query optimization'],
      impact: 'medium',
    },
  }),
});

// Bulk data generators
export const createMockUsers = (count: number): User[] =>
  Array.from({ length: count }, () => createMockUser());

export const createMockQueries = (count: number, userId?: string): Query[] =>
  Array.from({ length: count }, () => createMockQuery(userId ? { userId } : {}));

export const createMockReports = (count: number, userId?: string): Report[] =>
  Array.from({ length: count }, () => createMockReport(userId ? { userId } : {}));

// Database reset utilities for tests
export const resetTestDatabase = async () => {
  // This would be implemented to reset test database state
  console.log('Resetting test database...');
};

export const seedTestDatabase = async () => {
  // This would be implemented to seed test database with initial data
  console.log('Seeding test database...');
};

// Type definitions (these would normally be imported from your actual types)
interface User {
  id: string;
  username: string;
  email: string;
  hashedPassword: string;
  isActive: boolean;
  createdAt: Date;
  lastLogin: Date | null;
}

interface Session {
  id: string;
  userId: string;
  token: string;
  expiresAt: Date;
  createdAt: Date;
  isActive: boolean;
}

interface Query {
  id: string;
  userId: string;
  queryText: string;
  params: Record<string, any>;
  executionTime: number;
  createdAt: Date;
}

interface Report {
  id: string;
  userId: string;
  title: string;
  description: string;
  data: Record<string, any>;
  createdAt: Date;
}

interface Insight {
  id: string;
  queryId: string;
  type: string;
  details: Record<string, any>;
  createdAt: Date;
}

interface PowerBIReport {
  id: string;
  name: string;
  datasetId: string;
  embedUrl: string;
  accessToken: string;
  tokenExpiry: Date;
  createdDate: Date;
  modifiedDate: Date;
}

interface APIResponse<T> {
  success: boolean;
  data: T;
  message: string;
  timestamp: string;
}

interface APIError {
  success: boolean;
  error: {
    code: number;
    message: string;
    details: string;
  };
  timestamp: string;
}

interface CacheEntry {
  key: string;
  value: any;
  ttl: number;
  tags: string[];
  createdAt: Date;
}