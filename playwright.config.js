const { defineConfig } = require("@playwright/test");

const port = process.env.PORTFOLIO_TEST_PORT || "4173";


module.exports = defineConfig({
  testDir: "./tests",
  testMatch: "gallery.spec.js",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
    trace: "retain-on-failure",
  },
  webServer: {
    command: `bundle exec jekyll serve --host 127.0.0.1 --port ${port} --strict_front_matter`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
