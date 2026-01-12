import { ConfigResponse } from '../types/config';

const CONFIG_URL = 'https://storage.jonathanburnhams.com/api/collections/2?secret=05dc8c899d57550315abd2926bdb7c44';

let cookieValue: string | null = null;

export const ConfigService = {
  init: async (): Promise<void> => {
    try {
      const response = await fetch(CONFIG_URL);
      if (!response.ok) {
        console.error('Failed to fetch config:', response.status);
        return;
      }
      const data: ConfigResponse = await response.json();
      const cookieEntry = data.contents.find((c) => c.key === 'cookie');
      if (cookieEntry) {
        cookieValue = cookieEntry.value;
      }
    } catch (error) {
      console.error('Error initializing config:', error);
    }
  },

  getCookie: (): string | null => {
    return cookieValue;
  },
};
