import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { CollectionService } from '../../../src/services/collection';

describe('CollectionService', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should fetch collection data successfully', async () => {
    const mockResponse = {
      id: 2,
      name: 'tubes',
      description: 'Data for tubes app',
      secret: 'secret-123',
      contents: [
        {
          key: 'cookie',
          type: 'value',
          value: 'cookie-value'
        }
      ]
    };

    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const result = await CollectionService.getCollection(2);

    expect(global.fetch).toHaveBeenCalledWith(
      'https://storage.jonathanburnhams.com/api/collections/2',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      })
    );
    expect(result).toEqual(mockResponse);
  });

  it('should throw an error when fetch fails', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: false,
      status: 404,
    });

    await expect(CollectionService.getCollection(2)).rejects.toThrow('Failed to fetch collection: 404');
  });
});
