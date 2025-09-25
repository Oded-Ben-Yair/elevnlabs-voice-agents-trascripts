import { test, expect } from '@playwright/test';

test.describe('Visual Regression Tests', () => {
  // Configure visual testing
  test.beforeEach(async ({ page }) => {
    // Set consistent viewport for visual consistency
    await page.setViewportSize({ width: 1280, height: 720 });

    // Wait for fonts to load to prevent flaky visual tests
    await page.waitForLoadState('networkidle');

    // Hide dynamic elements that might cause false positives
    await page.addStyleTag({
      content: `
        .loading-spinner,
        .timestamp,
        .live-indicator {
          visibility: hidden !important;
        }
      `
    });
  });

  test('should match login page visual snapshot', async ({ page }) => {
    await page.goto('/login');

    // Wait for page to be fully loaded
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible();

    // Take screenshot with masked dynamic elements
    await expect(page).toHaveScreenshot('login-page.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('.version-info'),
        page.locator('.build-timestamp')
      ]
    });
  });

  test('should match dashboard visual snapshot', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpassword');
    await page.click('[data-testid="login-button"]');

    // Wait for dashboard to load
    await page.waitForURL('/dashboard');
    await expect(page.locator('[data-testid="dashboard-header"]')).toBeVisible();

    // Wait for data to load
    await expect(page.locator('[data-testid="recent-queries"]')).toBeVisible();
    await expect(page.locator('[data-testid="performance-metrics"]')).toBeVisible();

    // Mask dynamic content
    await expect(page).toHaveScreenshot('dashboard-page.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('[data-testid="last-updated"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match query builder visual snapshot', async ({ page }) => {
    // Navigate to query builder
    await page.goto('/dashboard');
    await page.click('[data-testid="new-query-button"]');

    await page.waitForURL('/query-builder');
    await expect(page.locator('[data-testid="query-builder"]')).toBeVisible();

    // Add some query content for visual consistency
    await page.fill('[data-testid="query-editor"]', 'SELECT * FROM users WHERE active = true');

    await expect(page).toHaveScreenshot('query-builder-page.png', {
      fullPage: true,
      animations: 'disabled'
    });
  });

  test('should match report creation modal visual snapshot', async ({ page }) => {
    await page.goto('/dashboard');

    // Open report creation modal
    await page.click('[data-testid="create-report-button"]');
    await expect(page.locator('[data-testid="report-modal"]')).toBeVisible();

    // Fill in some data for visual consistency
    await page.fill('[data-testid="report-title"]', 'Test Report');
    await page.fill('[data-testid="report-description"]', 'This is a test report for visual regression testing');

    await expect(page.locator('[data-testid="report-modal"]')).toHaveScreenshot('report-creation-modal.png', {
      animations: 'disabled'
    });
  });

  test('should match PowerBI reports page visual snapshot', async ({ page }) => {
    await page.goto('/powerbi');

    // Wait for reports to load
    await expect(page.locator('[data-testid="powerbi-reports"]')).toBeVisible();
    await expect(page.locator('[data-testid="report-item"]').first()).toBeVisible();

    await expect(page).toHaveScreenshot('powerbi-reports-page.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="last-refreshed"]'),
        page.locator('.refresh-timestamp')
      ]
    });
  });

  test('should match PowerBI embedded report visual snapshot', async ({ page }) => {
    await page.goto('/powerbi');

    // Click on first report to embed it
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="powerbi-embed"]')).toBeVisible();

    // Wait for iframe to load
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('powerbi-embedded-report.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="embed-iframe"]') // Mask the actual iframe content
      ]
    });
  });

  test('should match insights dashboard visual snapshot', async ({ page }) => {
    await page.goto('/insights');

    // Wait for insights to load
    await expect(page.locator('[data-testid="insights-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="insight-card"]').first()).toBeVisible();

    await expect(page).toHaveScreenshot('insights-dashboard.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="generated-timestamp"]'),
        page.locator('.confidence-score') // These might be animated
      ]
    });
  });

  test('should match user profile page visual snapshot', async ({ page }) => {
    await page.goto('/profile');

    await expect(page.locator('[data-testid="profile-form"]')).toBeVisible();

    await expect(page).toHaveScreenshot('user-profile-page.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="last-login"]'),
        page.locator('[data-testid="member-since"]')
      ]
    });
  });

  test('should match mobile dashboard view', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto('/dashboard');
    await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible();

    await expect(page).toHaveScreenshot('mobile-dashboard.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match tablet dashboard view', async ({ page }) => {
    // Set tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });

    await page.goto('/dashboard');
    await expect(page.locator('[data-testid="tablet-layout"]')).toBeVisible();

    await expect(page).toHaveScreenshot('tablet-dashboard.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match error page visual snapshot', async ({ page }) => {
    // Navigate to a non-existent page to trigger error
    await page.goto('/non-existent-page');

    await expect(page.locator('[data-testid="error-page"]')).toBeVisible();

    await expect(page).toHaveScreenshot('error-page.png', {
      fullPage: true,
      animations: 'disabled'
    });
  });

  test('should match loading states visual snapshot', async ({ page }) => {
    // Intercept API calls to delay them
    await page.route('**/api/queries/recent', async route => {
      await new Promise(resolve => setTimeout(resolve, 2000));
      await route.continue();
    });

    await page.goto('/dashboard');

    // Capture loading state
    await expect(page.locator('[data-testid="loading-spinner"]')).toBeVisible();

    await expect(page).toHaveScreenshot('dashboard-loading-state.png', {
      animations: 'disabled'
    });
  });

  test('should match empty state visual snapshots', async ({ page }) => {
    // Mock empty responses
    await page.route('**/api/queries/recent', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], success: true })
      });
    });

    await page.route('**/api/reports', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { reports: [] }, success: true })
      });
    });

    await page.goto('/dashboard');

    // Wait for empty state to appear
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible();

    await expect(page).toHaveScreenshot('dashboard-empty-state.png', {
      fullPage: true,
      animations: 'disabled'
    });
  });

  test('should match dark theme visual snapshots', async ({ page }) => {
    // Enable dark theme
    await page.goto('/dashboard');
    await page.click('[data-testid="theme-toggle"]');

    // Wait for theme to apply
    await expect(page.locator('body')).toHaveClass(/dark-theme/);

    await expect(page).toHaveScreenshot('dashboard-dark-theme.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match high contrast theme visual snapshots', async ({ page }) => {
    // Enable high contrast theme
    await page.goto('/dashboard');
    await page.click('[data-testid="accessibility-menu"]');
    await page.click('[data-testid="high-contrast-toggle"]');

    // Wait for theme to apply
    await expect(page.locator('body')).toHaveClass(/high-contrast/);

    await expect(page).toHaveScreenshot('dashboard-high-contrast.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match notification states visual snapshots', async ({ page }) => {
    await page.goto('/dashboard');

    // Trigger success notification
    await page.evaluate(() => {
      window.showNotification?.('Query executed successfully', 'success');
    });

    await expect(page.locator('[data-testid="notification-success"]')).toBeVisible();

    await expect(page).toHaveScreenshot('success-notification.png', {
      clip: { x: 0, y: 0, width: 400, height: 100 },
      animations: 'disabled'
    });

    // Trigger error notification
    await page.evaluate(() => {
      window.showNotification?.('Query execution failed', 'error');
    });

    await expect(page.locator('[data-testid="notification-error"]')).toBeVisible();

    await expect(page).toHaveScreenshot('error-notification.png', {
      clip: { x: 0, y: 0, width: 400, height: 100 },
      animations: 'disabled'
    });
  });

  test('should match component states across different browsers', async ({ page, browserName }) => {
    await page.goto('/dashboard');
    await expect(page.locator('[data-testid="dashboard-header"]')).toBeVisible();

    // Take browser-specific screenshot
    await expect(page).toHaveScreenshot(`dashboard-${browserName}.png`, {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('[data-testid="live-metrics"]'),
        page.locator('.timestamp')
      ]
    });
  });

  test('should match form validation states', async ({ page }) => {
    await page.goto('/login');

    // Trigger validation errors
    await page.click('[data-testid="login-button"]');

    await expect(page.locator('[data-testid="email-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="password-error"]')).toBeVisible();

    await expect(page.locator('[data-testid="login-form"]')).toHaveScreenshot('form-validation-errors.png', {
      animations: 'disabled'
    });
  });
});