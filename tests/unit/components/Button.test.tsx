import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from '@/src/components/Button';
import { describe, it, expect, vi } from 'vitest';

describe('Button Component', () => {
  it('renders with the correct label', () => {
    const label = 'Click Me';
    render(<Button label={label} onClick={() => {}} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('calls onClick handler when clicked', () => {
    const handleClick = vi.fn();
    render(<Button label="Click Me" onClick={handleClick} />);
    fireEvent.click(screen.getByText('Click Me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when the disabled prop is true', () => {
    render(<Button label="Disabled" onClick={() => {}} disabled />);
    expect(screen.getByText('Disabled').closest('button')).toBeDisabled();
  });

  it('applies the primary variant class by default', () => {
    render(<Button label="Primary" onClick={() => {}} />);
    const button = screen.getByText('Primary').closest('button');
    expect(button).toHaveClass('button-primary');
  });

  it('applies the secondary variant class when specified', () => {
    render(<Button label="Secondary" onClick={() => {}} variant="secondary" />);
    const button = screen.getByText('Secondary').closest('button');
    expect(button).toHaveClass('button-secondary');
  });
});
