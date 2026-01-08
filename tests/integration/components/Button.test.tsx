
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '@/src/components/Button';

describe('Button Component', () => {
  it('renders button with label', () => {
    render(<Button label="Click me" onClick={() => {}} />);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();

    render(<Button label="Click me" onClick={handleClick} />);

    await user.click(screen.getByTestId('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('does not call onClick when disabled', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();

    render(<Button label="Click me" onClick={handleClick} disabled />);

    await user.click(screen.getByTestId('button'));
    expect(handleClick).not.toHaveBeenCalled();
  });

  it('applies primary variant class by default', () => {
    render(<Button label="Click me" onClick={() => {}} />);
    const button = screen.getByTestId('button');
    expect(button).toHaveClass('button-primary');
  });

  it('applies secondary variant class when specified', () => {
    render(<Button label="Click me" onClick={() => {}} variant="secondary" />);
    const button = screen.getByTestId('button');
    expect(button).toHaveClass('button-secondary');
  });

  it('is disabled when disabled prop is true', () => {
    render(<Button label="Click me" onClick={() => {}} disabled />);
    expect(screen.getByTestId('button')).toBeDisabled();
  });
});
