import { FullConfig } from '@playwright/test';
import { resetTestDatabase } from '../fixtures/test-data';
import fs from 'fs';
import path from 'path';

async function globalTeardown(config: FullConfig) {
  // Clean up test database
  await resetTestDatabase();

  // Remove authentication state file
  const authStatePath = path.join(__dirname, 'auth-state.json');
  if (fs.existsSync(authStatePath)) {
    fs.unlinkSync(authStatePath);
  }

  // Clean up test artifacts
  const artifactsDir = path.join(__dirname, '../../test-results');
  if (fs.existsSync(artifactsDir)) {
    // Keep test results but clean up temporary files
    console.log('Test artifacts preserved in:', artifactsDir);
  }

  console.log('Global teardown completed successfully');
}

export default globalTeardown;