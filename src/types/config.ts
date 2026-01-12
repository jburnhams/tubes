export interface ConfigContent {
  key: string;
  type: string;
  value: string;
}

export interface ConfigResponse {
  id: number;
  name: string;
  description: string;
  secret: string;
  user_id: number;
  created_at: string;
  updated_at: string;
  metadata: unknown;
  origin: string;
  contents: ConfigContent[];
}
