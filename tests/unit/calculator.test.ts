
import { add, subtract, multiply, divide, percentage } from '@/src/services/calculator';

describe('Calculator Service', () => {
  describe('add', () => {
    it('adds two positive numbers', () => {
      expect(add(2, 3)).toBe(5);
    });

    it('adds negative numbers', () => {
      expect(add(-2, -3)).toBe(-5);
    });

    it('adds positive and negative numbers', () => {
      expect(add(5, -3)).toBe(2);
    });
  });

  describe('subtract', () => {
    it('subtracts two positive numbers', () => {
      expect(subtract(5, 3)).toBe(2);
    });

    it('subtracts negative numbers', () => {
      expect(subtract(-5, -3)).toBe(-2);
    });

    it('subtracts resulting in negative', () => {
      expect(subtract(3, 5)).toBe(-2);
    });
  });

  describe('multiply', () => {
    it('multiplies two positive numbers', () => {
      expect(multiply(4, 5)).toBe(20);
    });

    it('multiplies by zero', () => {
      expect(multiply(4, 0)).toBe(0);
    });

    it('multiplies negative numbers', () => {
      expect(multiply(-4, -5)).toBe(20);
    });

    it('multiplies positive and negative', () => {
      expect(multiply(4, -5)).toBe(-20);
    });
  });

  describe('divide', () => {
    it('divides two positive numbers', () => {
      expect(divide(10, 2)).toBe(5);
    });

    it('divides resulting in decimal', () => {
      expect(divide(5, 2)).toBe(2.5);
    });

    it('throws error when dividing by zero', () => {
      expect(() => divide(10, 0)).toThrow('Cannot divide by zero');
    });

    it('divides negative numbers', () => {
      expect(divide(-10, -2)).toBe(5);
    });
  });

  describe('percentage', () => {
    it('calculates percentage correctly', () => {
      expect(percentage(25, 100)).toBe(25);
    });

    it('calculates percentage with decimals', () => {
      expect(percentage(1, 3)).toBeCloseTo(33.333, 2);
    });

    it('returns 0 when total is 0', () => {
      expect(percentage(5, 0)).toBe(0);
    });

    it('calculates percentage greater than 100', () => {
      expect(percentage(150, 100)).toBe(150);
    });
  });
});
