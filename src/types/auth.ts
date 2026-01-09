export interface User {
  id: number;
  email: string;
  name: string;
  profile_picture: string;
  is_admin: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string;
}

export interface AuthErrorResponse {
  error: string;
  message: string;
  login_url: string;
}
