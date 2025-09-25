import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should redirect to login page when not authenticated', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/.*\/login/);
  });

  test('should login with valid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');

    await page.click('[data-testid="login-button"]');

    await expect(page).toHaveURL(/.*\/dashboard/);
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email"]', 'invalid@example.com');
    await page.fill('[data-testid="password"]', 'wrongpassword');

    await page.click('[data-testid="login-button"]');

    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-message"]')).toContainText('Invalid credentials');
  });

  test('should validate email format', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email"]', 'invalid-email');
    await page.fill('[data-testid="password"]', 'password');

    await page.click('[data-testid="login-button"]');

    await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="email-error"]')).toContainText('Invalid email format');
  });

  test('should logout successfully', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');
    await page.click('[data-testid="login-button"]');

    await expect(page).toHaveURL(/.*\/dashboard/);

    // Logout
    await page.click('[data-testid="user-menu"]');
    await page.click('[data-testid="logout-button"]');

    await expect(page).toHaveURL(/.*\/login/);
    await expect(page.locator('[data-testid="user-menu"]')).not.toBeVisible();
  });

  test('should remember login state after page refresh', async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');
    await page.click('[data-testid="login-button"]');

    await expect(page).toHaveURL(/.*\/dashboard/);

    // Refresh page
    await page.reload();

    // Should still be logged in
    await expect(page).toHaveURL(/.*\/dashboard/);
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
  });

  test('should handle session expiry', async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');
    await page.click('[data-testid="login-button"]');

    await expect(page).toHaveURL(/.*\/dashboard/);

    // Mock session expiry by clearing localStorage
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    // Try to access protected route
    await page.goto('/dashboard');

    // Should redirect to login
    await expect(page).toHaveURL(/.*\/login/);
  });

  test('should show loading state during login', async ({ page }) => {
    await page.goto('/login');

    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');

    // Intercept login request to add delay
    await page.route('**/api/auth/login', async (route) => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.continue();
    });

    await page.click('[data-testid="login-button"]');

    // Should show loading state
    await expect(page.locator('[data-testid="login-loading"]')).toBeVisible();

    // Wait for login to complete
    await expect(page).toHaveURL(/.*\/dashboard/);
  });

  test('should handle password visibility toggle', async ({ page }) => {
    await page.goto('/login');

    const passwordInput = page.locator('[data-testid="password"]');
    const toggleButton = page.locator('[data-testid="password-toggle"]');

    await passwordInput.fill('testpassword');

    // Password should be hidden by default
    await expect(passwordInput).toHaveAttribute('type', 'password');

    // Toggle to show password
    await toggleButton.click();
    await expect(passwordInput).toHaveAttribute('type', 'text');

    // Toggle back to hide password
    await toggleButton.click();
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });
});