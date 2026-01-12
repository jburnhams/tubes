export interface CollectionContent {
  key: string;
  type: string;
  value: string;
}

export interface CollectionResponse {
  id: number;
  name: string;
  description: string;
  secret: string;
  contents: CollectionContent[];
}
