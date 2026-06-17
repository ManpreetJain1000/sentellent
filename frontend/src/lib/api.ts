const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export const googleAuthStartUrl = `${API_BASE_URL}/api/v1/auth/google/start`;
export const googleAuthReconnectUrl = `${API_BASE_URL}/api/v1/auth/google/reconnect`;

export type ApiError = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
};

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  user: User;
};

export type Conversation = {
  id: string;
  organization_id: string;
  user_id: string | null;
  title: string | null;
  status: string;
  expires_at: string;
  created_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  sent_at: string;
};

export type MemoryItem = {
  id: string;
  memory_type: string;
  content: string;
  source_type: string;
  source_kind?: string | null;
  visibility: string;
  pinned_at?: string | null;
  corrected_at?: string | null;
  created_at: string;
};

export type WorkspaceConnection = {
  provider: string;
  email: string | null;
  scopes: string[];
  is_connected: boolean;
  token_expires_at: string | null;
  has_gmail_access: boolean;
  has_calendar_access: boolean;
  has_calendar_write_access: boolean;
  needs_reconnect: boolean;
  reconnect_url: string | null;
};

async function request<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method ?? "GET").toUpperCase();
  const hasBody = options.body != null && options.body !== "";

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    method,
    headers,
  });

  if (!response.ok) {
    let message = "Request failed";
    try {
      const error = (await response.json()) as ApiError;
      message = error.error?.message ?? message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiRequestError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  me(token: string) {
    return request<User>("/api/v1/auth/me", {}, token);
  },
  workspaceStatus(token: string) {
    return request<WorkspaceConnection>("/api/v1/auth/workspace", {}, token);
  },
  listConversations(token: string) {
    return request<{ items: Conversation[] }>("/api/v1/conversations", {}, token);
  },
  createConversation(token: string, title?: string) {
    return request<Conversation>(
      "/api/v1/conversations",
      {
        method: "POST",
        body: JSON.stringify({ title }),
      },
      token,
    );
  },
  deleteConversation(token: string, conversationId: string) {
    return request<void>(
      `/api/v1/conversations/${conversationId}`,
      {
        method: "DELETE",
      },
      token,
    );
  },
  listMessages(token: string, conversationId: string) {
    return request<{ items: Message[] }>(`/api/v1/conversations/${conversationId}/messages`, {}, token);
  },
  sendMessage(token: string, conversationId: string, content: string) {
    return request<{
      user_message: Message;
      assistant_message: Message;
      memories_used: string[];
      email_memories_learned: number;
    }>(
      `/api/v1/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ content }),
      },
      token,
    );
  },
  listMemory(token: string) {
    return request<{ items: MemoryItem[] }>("/api/v1/memory", {}, token);
  },
  correctMemory(token: string, memoryId: string, content: string) {
    return request<MemoryItem>(
      `/api/v1/memory/${memoryId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ content }),
      },
      token,
    );
  },
  forgetMemory(token: string, memoryId: string) {
    return request<MemoryItem>(
      `/api/v1/memory/${memoryId}/forget`,
      {
        method: "POST",
      },
      token,
    );
  },
  pinMemory(token: string, memoryId: string) {
    return request<MemoryItem>(
      `/api/v1/memory/${memoryId}/pin`,
      {
        method: "POST",
      },
      token,
    );
  },
};

export const authStorage = {
  getToken() {
    return localStorage.getItem("sentellent_token");
  },
  setToken(token: string) {
    localStorage.setItem("sentellent_token", token);
  },
  clear() {
    localStorage.removeItem("sentellent_token");
  },
};
