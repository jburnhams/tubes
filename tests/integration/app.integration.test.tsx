
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as fs from 'fs';
import * as path from 'path';
import App from '@/src/App';

describe('Browser Integration Tests', () => {
  describe('index.html structure', () => {
    let htmlContent: string;

    beforeEach(() => {
      htmlContent = fs.readFileSync(
        path.join(__dirname, '..', '..', 'index.html'),
        'utf-8'
      );
    });

    it('has valid HTML structure with doctype', () => {
      expect(htmlContent).toMatch(/^<!doctype html>/i);
    });

    it('has correct language attribute', () => {
      expect(htmlContent).toMatch(/<html[^>]+lang="en"/i);
    });

    it('has required meta tags', () => {
      expect(htmlContent).toMatch(/<meta\s+charset="UTF-8"\s*\/?>/i);
      expect(htmlContent).toMatch(/<meta\s+name="viewport"\s+content="[^"]*width=device-width[^"]*"\s*\/?>/i);
    });

    it('has a title element', () => {
      const titleMatch = htmlContent.match(/<title>([^<]+)<\/title>/i);
      expect(titleMatch).toBeTruthy();
      expect(titleMatch?.[1]).toBeTruthy();
      expect(titleMatch?.[1].length).toBeGreaterThan(0);
    });

    it('has root div with correct id', () => {
      expect(htmlContent).toMatch(/<div\s+id="root"[^>]*>/i);
    });

    it('has main script tag pointing to correct entry point', () => {
      expect(htmlContent).toMatch(/<script\s+type="module"\s+src="\/src\/main\.tsx"[^>]*>/i);
    });

    it('has favicon link', () => {
      expect(htmlContent).toMatch(/<link\s+rel="icon"/i);
    });

    it('has proper HTML5 structure', () => {
      // Check for essential HTML5 elements
      expect(htmlContent).toContain('<head>');
      expect(htmlContent).toContain('</head>');
      expect(htmlContent).toContain('<body>');
      expect(htmlContent).toContain('</body>');
      expect(htmlContent).toContain('</html>');
    });
  });

  describe('App component integration', () => {
    it('renders the app with all required elements', () => {
      render(<App />);

      // Check main heading
      expect(screen.getByText('JS App Template')).toBeInTheDocument();

      // Check description
      expect(
        screen.getByText(/A minimal React \+ TypeScript app/i)
      ).toBeInTheDocument();

      // Check counter is displayed
      expect(screen.getByText(/Counter:/i)).toBeInTheDocument();

      // Check all buttons are present
      expect(screen.getByText('Increment')).toBeInTheDocument();
      expect(screen.getByText('Decrement')).toBeInTheDocument();
      expect(screen.getByText('Reset')).toBeInTheDocument();
    });

    it('counter starts at 0', () => {
      render(<App />);
      expect(screen.getByText('Counter: 0')).toBeInTheDocument();
    });

    it('increments counter when increment button is clicked', async () => {
      const user = userEvent.setup();
      render(<App />);

      const incrementButton = screen.getByText('Increment');
      await user.click(incrementButton);

      expect(screen.getByText('Counter: 1')).toBeInTheDocument();
    });

    it('decrements counter when decrement button is clicked', async () => {
      const user = userEvent.setup();
      render(<App />);

      const decrementButton = screen.getByText('Decrement');
      await user.click(decrementButton);

      expect(screen.getByText('Counter: -1')).toBeInTheDocument();
    });

    it('resets counter when reset button is clicked', async () => {
      const user = userEvent.setup();
      render(<App />);

      // Increment a few times
      const incrementButton = screen.getByText('Increment');
      await user.click(incrementButton);
      await user.click(incrementButton);
      await user.click(incrementButton);

      expect(screen.getByText('Counter: 3')).toBeInTheDocument();

      // Reset
      const resetButton = screen.getByText('Reset');
      await user.click(resetButton);

      expect(screen.getByText('Counter: 0')).toBeInTheDocument();
    });

    it('handles multiple interactions correctly', async () => {
      const user = userEvent.setup();
      render(<App />);

      const incrementButton = screen.getByText('Increment');
      const decrementButton = screen.getByText('Decrement');
      const resetButton = screen.getByText('Reset');

      // Complex sequence of operations
      await user.click(incrementButton);
      await user.click(incrementButton);
      expect(screen.getByText('Counter: 2')).toBeInTheDocument();

      await user.click(decrementButton);
      expect(screen.getByText('Counter: 1')).toBeInTheDocument();

      await user.click(incrementButton);
      await user.click(incrementButton);
      await user.click(incrementButton);
      expect(screen.getByText('Counter: 4')).toBeInTheDocument();

      await user.click(resetButton);
      expect(screen.getByText('Counter: 0')).toBeInTheDocument();

      await user.click(decrementButton);
      await user.click(decrementButton);
      expect(screen.getByText('Counter: -2')).toBeInTheDocument();
    });

    it('renders correct CSS classes for app structure', () => {
      const { container } = render(<App />);

      const appDiv = container.querySelector('.app');
      expect(appDiv).toBeInTheDocument();

      const counterDemo = container.querySelector('.counter-demo');
      expect(counterDemo).toBeInTheDocument();

      const buttonGroup = container.querySelector('.button-group');
      expect(buttonGroup).toBeInTheDocument();
    });

    it('has correct button variants', () => {
      render(<App />);

      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(3);

      // Check that buttons have the appropriate classes
      const incrementButton = screen.getByText('Increment').closest('button');
      const decrementButton = screen.getByText('Decrement').closest('button');
      const resetButton = screen.getByText('Reset').closest('button');

      expect(incrementButton).toHaveClass('button-primary');
      expect(decrementButton).toHaveClass('button-secondary');
      expect(resetButton).toHaveClass('button-secondary');
    });
  });

  describe('Full page rendering simulation', () => {
    it('simulates complete page load and interaction flow', async () => {
      const user = userEvent.setup();

      // Verify index.html exists and has root element
      const html = fs.readFileSync(
        path.join(__dirname, '..', '..', 'index.html'),
        'utf-8'
      );
      expect(html).toContain('id="root"');

      // Render the React app in jsdom environment (simulating what main.tsx does)
      render(<App />);

      // Verify initial state
      expect(screen.getByText('JS App Template')).toBeInTheDocument();
      expect(screen.getByText('Counter: 0')).toBeInTheDocument();

      // Simulate user workflow
      await user.click(screen.getByText('Increment'));
      await user.click(screen.getByText('Increment'));
      await user.click(screen.getByText('Increment'));

      expect(screen.getByText('Counter: 3')).toBeInTheDocument();

      await user.click(screen.getByText('Decrement'));
      expect(screen.getByText('Counter: 2')).toBeInTheDocument();

      await user.click(screen.getByText('Reset'));
      expect(screen.getByText('Counter: 0')).toBeInTheDocument();
    });
  });
});
