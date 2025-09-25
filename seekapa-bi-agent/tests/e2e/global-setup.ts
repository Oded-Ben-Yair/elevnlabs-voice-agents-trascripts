import { chromium, FullConfig } from '@playwright/test';
import { resetTestDatabase, seedTestDatabase } from '../fixtures/test-data';

async function globalSetup(config: FullConfig) {
  // Reset and seed test database
  await resetTestDatabase();
  await seedTestDatabase();

  // Create a browser instance for authentication
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Perform authentication and save state
  await page.goto('/login');
  await page.fill('[data-testid="email"]', 'test@example.com');
  await page.fill('[data-testid="password"]', 'testpassword');
  await page.click('[data-testid="login-button"]');

  // Wait for successful authentication
  await page.waitForURL('/dashboard');

  // Save authenticated state
  await context.storageState({ path: 'tests/e2e/auth-state.json' });

  await context.close();
  await browser.close();

  console.log('Global setup completed successfully');
}

export default globalSetup;