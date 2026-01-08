# Repository Guidelines

- Application code lives under `src/` at the repository root.
- Test code lives under `tests/` and is grouped by type:
  - `tests/unit/` contains fast, isolated tests that rely on mocks.
  - `tests/integration/` contains slower end-to-end style tests or those touching external resources such as the filesystem.
  - `tests/utils/` stores shared test utilities (for example, the Jest setup file).
- Use the npm scripts to target the correct suites:
  - `npm run test:unit` (or `npm run test:coverage`) runs only the unit tests.
  - `npm run test:integration` runs only the integration suite.
- Code coverage must be calculated from the unit suite only.
- GitHub Actions enforce this separation: the standard workflow runs unit tests with coverage, while a dedicated workflow runs the integration suite on Node.js 25.
