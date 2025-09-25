import { test, expect } from '@playwright/test';

test.describe('Dashboard Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Use authenticated state
    await page.goto('/dashboard');
  });

  test('should display dashboard with all main components', async ({ page }) => {
    // Check main dashboard elements are present
    await expect(page.locator('[data-testid="dashboard-header"]')).toBeVisible();
    await expect(page.locator('[data-testid="sidebar-nav"]')).toBeVisible();
    await expect(page.locator('[data-testid="main-content"]')).toBeVisible();
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
  });

  test('should display recent queries section', async ({ page }) => {
    await expect(page.locator('[data-testid="recent-queries"]')).toBeVisible();
    await expect(page.locator('[data-testid="recent-queries-title"]')).toContainText('Recent Queries');

    // Check if queries are displayed
    const queryItems = page.locator('[data-testid="query-item"]');
    await expect(queryItems).toHaveCount.greaterThan(0);
  });

  test('should display performance metrics', async ({ page }) => {
    await expect(page.locator('[data-testid="performance-metrics"]')).toBeVisible();

    // Check for key metrics
    await expect(page.locator('[data-testid="metric-total-queries"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-avg-response-time"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-success-rate"]')).toBeVisible();
  });

  test('should display insights dashboard', async ({ page }) => {
    await expect(page.locator('[data-testid="insights-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="insights-title"]')).toContainText('AI Insights');

    // Check for insight cards
    const insightCards = page.locator('[data-testid="insight-card"]');
    await expect(insightCards).toHaveCount.greaterThan(0);
  });

  test('should navigate to query builder from dashboard', async ({ page }) => {
    await page.click('[data-testid="new-query-button"]');

    await expect(page).toHaveURL(/.*\/query-builder/);
    await expect(page.locator('[data-testid="query-builder"]')).toBeVisible();
  });

  test('should filter recent queries', async ({ page }) => {
    // Wait for queries to load
    await expect(page.locator('[data-testid="query-item"]').first()).toBeVisible();

    // Apply date filter
    await page.click('[data-testid="date-filter"]');
    await page.click('[data-testid="filter-last-7-days"]');

    // Verify filter is applied
    await expect(page.locator('[data-testid="active-filter"]')).toContainText('Last 7 days');

    // Check that queries are filtered
    const filteredQueries = page.locator('[data-testid="query-item"]');
    await expect(filteredQueries).toHaveCount.greaterThan(0);
  });

  test('should search recent queries', async ({ page }) => {
    const searchInput = page.locator('[data-testid="query-search"]');

    await searchInput.fill('SELECT');
    await page.keyboard.press('Enter');

    // Wait for search results
    await page.waitForTimeout(500);

    // Check that search results contain the search term
    const queryItems = page.locator('[data-testid="query-item"]');
    const firstQuery = queryItems.first();
    await expect(firstQuery).toContainText('SELECT', { ignoreCase: true });
  });

  test('should display quick stats correctly', async ({ page }) => {
    // Check that stats are displayed with proper formatting
    const totalQueries = page.locator('[data-testid="stat-total-queries"]');
    const avgTime = page.locator('[data-testid="stat-avg-time"]');

    await expect(totalQueries).toBeVisible();
    await expect(avgTime).toBeVisible();

    // Verify numeric formatting
    const totalQueriesText = await totalQueries.textContent();
    const avgTimeText = await avgTime.textContent();

    expect(totalQueriesText).toMatch(/^\d+/); // Should start with a number
    expect(avgTimeText).toMatch(/\d+\s*ms/); // Should contain ms unit
  });

  test('should handle empty state for new users', async ({ page }) => {
    // Mock empty state by intercepting API calls
    await page.route('**/api/queries/recent', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], success: true }),
      });
    });

    await page.reload();

    // Check empty state is displayed
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible();
    await expect(page.locator('[data-testid="empty-state-message"]')).toContainText('No queries yet');
    await expect(page.locator('[data-testid="get-started-button"]')).toBeVisible();
  });

  test('should refresh dashboard data', async ({ page }) => {
    // Wait for initial load
    await expect(page.locator('[data-testid="query-item"]').first()).toBeVisible();

    // Click refresh button
    await page.click('[data-testid="refresh-button"]');

    // Check loading state
    await expect(page.locator('[data-testid="loading-spinner"]')).toBeVisible();

    // Wait for refresh to complete
    await expect(page.locator('[data-testid="loading-spinner"]')).not.toBeVisible();

    // Verify data is still displayed
    await expect(page.locator('[data-testid="query-item"]').first()).toBeVisible();
  });

  test('should handle API errors gracefully', async ({ page }) => {
    // Mock API error
    await page.route('**/api/queries/recent', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Internal Server Error' }),
      });
    });

    await page.reload();

    // Check error state is displayed
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-message"]')).toContainText('Failed to load');
    await expect(page.locator('[data-testid="retry-button"]')).toBeVisible();
  });

  test('should open query details modal', async ({ page }) => {
    // Wait for queries to load
    await expect(page.locator('[data-testid="query-item"]').first()).toBeVisible();

    // Click on first query
    await page.click('[data-testid="query-item"]');

    // Check modal opens
    await expect(page.locator('[data-testid="query-modal"]')).toBeVisible();
    await expect(page.locator('[data-testid="query-details"]')).toBeVisible();
    await expect(page.locator('[data-testid="query-execution-time"]')).toBeVisible();

    // Close modal
    await page.click('[data-testid="close-modal"]');
    await expect(page.locator('[data-testid="query-modal"]')).not.toBeVisible();
  });

  test('should display tooltips for metric explanations', async ({ page }) => {
    // Hover over metric to show tooltip
    await page.hover('[data-testid="metric-avg-response-time"]');

    // Check tooltip appears
    await expect(page.locator('[data-testid="tooltip"]')).toBeVisible();
    await expect(page.locator('[data-testid="tooltip"]')).toContainText('Average time taken');

    // Move away to hide tooltip
    await page.hover('[data-testid="dashboard-header"]');
    await expect(page.locator('[data-testid="tooltip"]')).not.toBeVisible();
  });
});