# JS App Template

A production-ready template for building React + TypeScript web applications with comprehensive testing infrastructure, CI/CD, and modern build tools.

## Features

- **React 19** with TypeScript in strict mode
- **Vite 7** for lightning-fast development and optimized builds
- **Jest 29** with React Testing Library for unit and integration tests
- **Coverage reporting** with 80% threshold (lines, statements), 85% (functions), 70% (branches)
- **GitHub Actions** CI/CD pipeline testing on Node.js 20.x, 22.x, and 24.x
- **ESM-first** architecture with proper module resolution
- **Path aliases** (@/*) for cleaner imports

## Quick Start

### 1. Clone this template

```bash
git clone <your-repo-url> my-new-app
cd my-new-app
```

### 2. Install dependencies

```bash
npm install
```

### 3. Start development server

```bash
npm run dev
```

Visit http://localhost:3000 to see your app.

### 4. Run tests

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode for development
npm run test:watch
```

## Project Structure

```
js-app-template/
├── src/
│   ├── components/      # React components
│   ├── services/        # Business logic and utilities
│   ├── hooks/           # Custom React hooks
│   ├── App.tsx          # Main application component
│   ├── main.tsx         # Application entry point
│   └── index.css        # Global styles
├── tests/
│   ├── setup.ts         # Jest test environment setup
│   ├── Button.test.tsx  # Example component test
│   ├── calculator.test.ts  # Example service test
│   └── useCounter.test.ts  # Example hook test
├── public/              # Static assets
├── .github/workflows/   # CI/CD configuration
│   └── node.js.yml      # GitHub Actions workflow
├── jest.config.js       # Jest configuration
├── tsconfig.json        # TypeScript configuration
├── vite.config.ts       # Vite configuration
├── babel.config.cjs     # Babel configuration
└── package.json         # Dependencies and scripts
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server on port 3000 |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview production build locally |
| `npm test` | Run all tests |
| `npm run test:coverage` | Run tests with coverage report |
| `npm run test:watch` | Run tests in watch mode |
| `npm run type-check` | Type-check without building |

## Testing

### Writing Tests

The template includes three types of example tests:

#### 1. Component Tests (`tests/Button.test.tsx`)

```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '@/src/components/Button';

it('calls onClick when clicked', async () => {
  const handleClick = jest.fn();
  const user = userEvent.setup();

  render(<Button label="Click" onClick={handleClick} />);
  await user.click(screen.getByTestId('button'));

  expect(handleClick).toHaveBeenCalledTimes(1);
});
```

#### 2. Service Tests (`tests/calculator.test.ts`)

```typescript
import { add, divide } from '@/src/services/calculator';

it('adds two numbers', () => {
  expect(add(2, 3)).toBe(5);
});

it('throws error when dividing by zero', () => {
  expect(() => divide(10, 0)).toThrow('Cannot divide by zero');
});
```

#### 3. Hook Tests (`tests/useCounter.test.ts`)

```typescript
import { renderHook, act } from '@testing-library/react';
import { useCounter } from '@/src/hooks/useCounter';

it('increments count', () => {
  const { result } = renderHook(() => useCounter(0));

  act(() => {
    result.current.increment();
  });

  expect(result.current.count).toBe(1);
});
```

### Coverage Thresholds

The project enforces minimum coverage thresholds:

- **Lines**: 80%
- **Functions**: 85%
- **Branches**: 70%
- **Statements**: 80%

Coverage reports are generated in the `coverage/` directory:
- `coverage/index.html` - Interactive HTML report
- `coverage/lcov.info` - LCOV format for CI/CD tools

## CI/CD

### GitHub Actions

The template includes a GitHub Actions workflow (`.github/workflows/node.js.yml`) that:

1. Runs on pushes and pull requests to the `main` branch
2. Tests on Node.js versions 20.x, 22.x, and 24.x
3. Installs dependencies with caching
4. Runs type checking and builds
5. Executes tests with coverage
6. Fails if tests fail or coverage thresholds aren't met

### Customizing the Workflow

Edit `.github/workflows/node.js.yml` to:
- Change target branches
- Add/remove Node.js versions
- Add deployment steps
- Integrate with external services

## Configuration

### TypeScript (`tsconfig.json`)

- **Target**: ES2022
- **Module**: ESNext (native ES modules)
- **Strict mode**: Enabled
- **Path aliases**: `@/*` maps to project root

### Vite (`vite.config.ts`)

- **Dev server**: Port 3000, listening on all interfaces
- **React plugin**: Fast Refresh enabled
- **Path aliases**: `@/` maps to project root

### Jest (`jest.config.js`)

- **Environment**: jsdom (browser-like)
- **Preset**: ts-jest for TypeScript support
- **Transform**: babel-jest for ESM compatibility
- **Coverage**: Collects from `src/**/*.{ts,tsx}`, excluding type definitions

### Babel (`babel.config.cjs`)

- **Presets**:
  - `@babel/preset-env` targeting current Node.js
  - `@babel/preset-typescript` for TypeScript support

## Customization Guide

### 1. Update Package Name

Edit `package.json`:

```json
{
  "name": "my-awesome-app",
  "version": "1.0.0",
  "description": "My awesome application"
}
```

### 2. Add ESM Dependencies to Transform

If you install ESM-only packages that need transformation, add them to `jest.config.js`:

```javascript
transformIgnorePatterns: [
  'node_modules/(?!(your-esm-package|another-package)/)',
],
```

### 3. Adjust Coverage Thresholds

Edit `jest.config.js` if the default thresholds are too strict/lenient:

```javascript
coverageThreshold: {
  global: {
    lines: 75,      // Lower if needed
    functions: 80,
    branches: 65,
    statements: 75,
  },
},
```

### 4. Add Environment Variables

For development, create `.env.local` (gitignored):

```bash
VITE_API_URL=http://localhost:3001
```

Access in code:

```typescript
const apiUrl = import.meta.env.VITE_API_URL;
```

Update `vite.config.ts` for more complex environment variable handling.

### 5. Remove Example Code

When starting your project, remove:

```bash
rm src/components/Button.tsx
rm src/services/calculator.ts
rm src/hooks/useCounter.ts
rm tests/Button.test.tsx
rm tests/calculator.test.ts
rm tests/useCounter.test.ts
```

Then update `src/App.tsx` with your own components.

## Best Practices

### File Organization

- **Components**: React UI components in `src/components/`
- **Services**: Business logic, API calls, utilities in `src/services/`
- **Hooks**: Custom React hooks in `src/hooks/`
- **Tests**: All tests in `tests/` directory matching `*.test.{ts,tsx}`

### Test File Naming

- Component tests: `ComponentName.test.tsx`
- Service/utility tests: `serviceName.test.ts`
- Hook tests: `useHookName.test.ts`

### Path Aliases

Use `@/` prefix for absolute imports:

```typescript
// Good
import { Button } from '@/src/components/Button';
import { add } from '@/src/services/calculator';

// Avoid
import { Button } from '../../components/Button';
```

### Test Coverage

- Aim for meaningful tests, not just coverage numbers
- Focus on testing behavior, not implementation details
- Test edge cases and error conditions
- Use descriptive test names

## Troubleshooting

### Tests Failing with Module Resolution Errors

If you see `Cannot find module` errors:

1. Check that path aliases in `jest.config.js` match `tsconfig.json`
2. Verify ESM packages are listed in `transformIgnorePatterns`
3. Ensure `.js` extension mapping is configured in `moduleNameMapper`

### Memory Issues During Tests

If tests crash with out-of-memory errors:

1. Increase `NODE_OPTIONS` in package.json scripts
2. Reduce `maxWorkers` in `jest.config.js`
3. Adjust `workerIdleMemoryLimit` setting

### Vite Build Errors

If the build fails:

1. Run `npm run type-check` to see TypeScript errors
2. Check that all imports use correct file extensions
3. Verify that environment variables are prefixed with `VITE_`

## Requirements

- **Node.js**: >= 20.0.0
- **npm**: 7.x or higher (comes with Node.js 20+)

## License

This template is open source and available under the MIT License.

## Contributing

Feel free to customize this template for your needs. Common customizations:

- Add linting (ESLint, Prettier)
- Add styling solutions (Tailwind, styled-components)
- Add routing (React Router)
- Add state management (Redux, Zustand, Jotai)
- Add API client libraries (axios, React Query)
- Add UI component libraries (Material-UI, Chakra UI)

## Support

For issues with:
- **This template**: Create an issue in your repository
- **Vite**: https://github.com/vitejs/vite
- **Jest**: https://jestjs.io/
- **React Testing Library**: https://testing-library.com/

## Acknowledgments

This template is inspired by modern React development best practices and includes testing infrastructure patterns from production applications.
