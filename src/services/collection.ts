import { CollectionResponse } from '../types/collection';

const COLLECTIONS_API_URL = 'https://storage.jonathanburnhams.com/api/collections';

export class CollectionService {
  static async getCollection(id: number): Promise<CollectionResponse> {
    const response = await fetch(`${COLLECTIONS_API_URL}/${id}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch collection: ${response.status}`);
    }

    return response.json();
  }
}
