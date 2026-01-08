import { renderHook, act } from '@testing-library/react';
import { useCounter } from '@/src/hooks/useCounter';
import { describe, it, expect } from 'vitest';

describe('useCounter Hook', () => {
  it('should initialize with default value', () => {
    const { result } = renderHook(() => useCounter());
    expect(result.current.count).toBe(0);
  });

  it('should initialize with provided value', () => {
    const { result } = renderHook(() => useCounter(10));
    expect(result.current.count).toBe(10);
  });

  it('should increment the counter', () => {
    const { result } = renderHook(() => useCounter(0));
    act(() => {
      result.current.increment();
    });
    expect(result.current.count).toBe(1);
  });

  it('should decrement the counter', () => {
    const { result } = renderHook(() => useCounter(0));
    act(() => {
      result.current.decrement();
    });
    expect(result.current.count).toBe(-1);
  });

  it('should reset the counter to initial value', () => {
    const { result } = renderHook(() => useCounter(10));

    act(() => {
      result.current.increment();
    });
    expect(result.current.count).toBe(11);

    act(() => {
      result.current.reset();
    });
    expect(result.current.count).toBe(10);
  });
});
