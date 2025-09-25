import { test, expect } from '@playwright/test';

test.describe('Power BI Integration', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/powerbi');
  });

  test('should display Power BI reports list', async ({ page }) => {
    await expect(page.locator('[data-testid="powerbi-reports"]')).toBeVisible();
    await expect(page.locator('[data-testid="reports-title"]')).toContainText('Power BI Reports');

    // Check if reports are loaded
    const reportItems = page.locator('[data-testid="report-item"]');
    await expect(reportItems).toHaveCount.greaterThan(0);
  });

  test('should embed Power BI report successfully', async ({ page }) => {
    // Click on first report
    await page.click('[data-testid="report-item"]');

    // Wait for embed to load
    await expect(page.locator('[data-testid="powerbi-embed"]')).toBeVisible();
    await expect(page.locator('[data-testid="embed-iframe"]')).toBeVisible();

    // Check embed has correct attributes
    const iframe = page.locator('[data-testid="embed-iframe"]');
    await expect(iframe).toHaveAttribute('src');
  });

  test('should handle Power BI authentication', async ({ page }) => {
    // Mock authentication flow
    await page.route('**/api/powerbi/authenticate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          accessToken: 'mock-access-token',
          expiresIn: 3600
        }),
      });
    });

    // Click authenticate button
    await page.click('[data-testid="authenticate-powerbi"]');

    // Check authentication success
    await expect(page.locator('[data-testid="auth-success"]')).toBeVisible();
    await expect(page.locator('[data-testid="auth-success"]')).toContainText('Successfully authenticated');
  });

  test('should filter reports by workspace', async ({ page }) => {
    // Open workspace filter
    await page.click('[data-testid="workspace-filter"]');

    // Select specific workspace
    await page.click('[data-testid="workspace-sales"]');

    // Verify filter is applied
    await expect(page.locator('[data-testid="active-filter"]')).toContainText('Sales');

    // Check filtered results
    const filteredReports = page.locator('[data-testid="report-item"]');
    await expect(filteredReports).toHaveCount.greaterThan(0);
  });

  test('should search for reports', async ({ page }) => {
    const searchInput = page.locator('[data-testid="report-search"]');

    await searchInput.fill('Sales Dashboard');
    await page.keyboard.press('Enter');

    // Wait for search results
    await page.waitForTimeout(500);

    // Check search results
    const reportItems = page.locator('[data-testid="report-item"]');
    const firstReport = reportItems.first();
    await expect(firstReport).toContainText('Sales', { ignoreCase: true });
  });

  test('should handle embed errors gracefully', async ({ page }) => {
    // Mock embed error
    await page.route('**/api/powerbi/reports/**/embed', async (route) => {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Insufficient permissions to access this report'
        }),
      });
    });

    await page.click('[data-testid="report-item"]');

    // Check error message is displayed
    await expect(page.locator('[data-testid="embed-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="embed-error"]')).toContainText('Insufficient permissions');
    await expect(page.locator('[data-testid="retry-embed"]')).toBeVisible();
  });

  test('should refresh report data', async ({ page }) => {
    // Load a report first
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="embed-iframe"]')).toBeVisible();

    // Click refresh button
    await page.click('[data-testid="refresh-report"]');

    // Check loading indicator
    await expect(page.locator('[data-testid="refresh-loading"]')).toBeVisible();

    // Wait for refresh to complete
    await expect(page.locator('[data-testid="refresh-loading"]')).not.toBeVisible();
  });

  test('should export report data', async ({ page }) => {
    // Load a report first
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="embed-iframe"]')).toBeVisible();

    // Start download
    const downloadPromise = page.waitForDownload();

    // Click export button
    await page.click('[data-testid="export-report"]');

    // Wait for download to start
    const download = await downloadPromise;

    // Verify download
    expect(download.suggestedFilename()).toMatch(/.*\.(pdf|xlsx)$/);
  });

  test('should handle full screen mode', async ({ page }) => {
    // Load a report first
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="embed-iframe"]')).toBeVisible();

    // Enter full screen
    await page.click('[data-testid="fullscreen-button"]');

    // Check full screen mode
    await expect(page.locator('[data-testid="powerbi-embed"]')).toHaveClass(/fullscreen/);

    // Exit full screen
    await page.keyboard.press('Escape');

    // Check normal mode restored
    await expect(page.locator('[data-testid="powerbi-embed"]')).not.toHaveClass(/fullscreen/);
  });

  test('should display report metadata', async ({ page }) => {
    // Click on report info button
    await page.click('[data-testid="report-info"]');

    // Check metadata modal
    await expect(page.locator('[data-testid="metadata-modal"]')).toBeVisible();
    await expect(page.locator('[data-testid="report-name"]')).toBeVisible();
    await expect(page.locator('[data-testid="last-updated"]')).toBeVisible();
    await expect(page.locator('[data-testid="dataset-info"]')).toBeVisible();

    // Close modal
    await page.click('[data-testid="close-metadata"]');
    await expect(page.locator('[data-testid="metadata-modal"]')).not.toBeVisible();
  });

  test('should handle responsive design', async ({ page }) => {
    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    // Check mobile layout
    await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible();
    await expect(page.locator('[data-testid="desktop-sidebar"]')).not.toBeVisible();

    // Load report in mobile view
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="mobile-embed"]')).toBeVisible();

    // Test tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });

    // Check tablet layout
    await expect(page.locator('[data-testid="tablet-layout"]')).toBeVisible();
  });

  test('should validate report access permissions', async ({ page }) => {
    // Mock permission check
    await page.route('**/api/powerbi/reports/**/permissions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          canView: true,
          canEdit: false,
          canShare: true
        }),
      });
    });

    await page.click('[data-testid="report-item"]');

    // Check permission-based UI
    await expect(page.locator('[data-testid="view-button"]')).toBeVisible();
    await expect(page.locator('[data-testid="edit-button"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="share-button"]')).toBeVisible();
  });

  test('should handle token expiration', async ({ page }) => {
    // Load report first
    await page.click('[data-testid="report-item"]');
    await expect(page.locator('[data-testid="embed-iframe"]')).toBeVisible();

    // Mock token expiration
    await page.route('**/api/powerbi/**', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Token expired'
        }),
      });
    });

    // Trigger action that requires token
    await page.click('[data-testid="refresh-report"]');

    // Check re-authentication flow
    await expect(page.locator('[data-testid="reauth-prompt"]')).toBeVisible();
    await expect(page.locator('[data-testid="reauth-button"]')).toBeVisible();
  });
});