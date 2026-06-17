import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { BrandMark } from "../components/BrandMark";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import {
  api,
  ApiRequestError,
  authStorage,
  Conversation,
  googleAuthReconnectUrl,
  MemoryItem,
  Message,
  User,
  WorkspaceConnection,
} from "../lib/api";

export function ChatPage() {
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [token, setToken] = useState<string | null>(authStorage.getToken());
  const [user, setUser] = useState<User | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceConnection | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [memoryItems, setMemoryItems] = useState<MemoryItem[]>([]);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editingMemoryContent, setEditingMemoryContent] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/login");
      return;
    }

    async function bootstrap() {
      try {
        const me = await api.me(token);
        setUser(me);

        const workspaceStatus = await api.workspaceStatus(token);
        setWorkspace(workspaceStatus);

        let conversationList: { items: Conversation[] } = { items: [] };
        let memoryList: { items: MemoryItem[] } = { items: [] };
        let conversationsLoaded = true;

        try {
          conversationList = await api.listConversations(token);
        } catch (conversationError) {
          conversationsLoaded = false;
          const message =
            conversationError instanceof Error
              ? conversationError.message
              : "Unable to load conversations.";
          setError(message);
        }

        try {
          memoryList = await api.listMemory(token);
        } catch (memoryError) {
          const memoryMessage =
            memoryError instanceof Error ? memoryError.message : "Unable to load memory.";
          setError((current) => current ?? memoryMessage);
        }

        setConversations(conversationList.items);
        setMemoryItems(memoryList.items);

        if (conversationList.items.length > 0) {
          const firstConversation = conversationList.items[0];
          setActiveConversationId(firstConversation.id);
          const messageList = await api.listMessages(token, firstConversation.id);
          setMessages(messageList.items);
        } else if (conversationsLoaded) {
          const conversation = await api.createConversation(token);
          setConversations([conversation]);
          setActiveConversationId(conversation.id);
          setMessages([]);
        }
      } catch (bootstrapError) {
        if (bootstrapError instanceof ApiRequestError && bootstrapError.status === 401) {
          authStorage.clear();
          navigate("/login");
          return;
        }
        const message =
          bootstrapError instanceof Error
            ? bootstrapError.message
            : "Unable to load your workspace.";
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
  }, [navigate, token]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function handleNewConversation() {
    if (!token) return;
    const conversation = await api.createConversation(token);
    setConversations((current) => [conversation, ...current]);
    setActiveConversationId(conversation.id);
    setMessages([]);
  }

  async function handleSelectConversation(conversationId: string) {
    if (!token) return;
    setActiveConversationId(conversationId);
    const messageList = await api.listMessages(token, conversationId);
    setMessages(messageList.items);
  }

  async function handleDeleteConversation(conversationId: string) {
    if (!token) return;

    const confirmed = window.confirm("Delete this conversation? This cannot be undone.");
    if (!confirmed) return;

    setError(null);
    try {
      await api.deleteConversation(token, conversationId);
      const remaining = conversations.filter((conversation) => conversation.id !== conversationId);
      setConversations(remaining);

      if (activeConversationId !== conversationId) {
        return;
      }

      if (remaining.length > 0) {
        const nextConversation = remaining[0];
        setActiveConversationId(nextConversation.id);
        const messageList = await api.listMessages(token, nextConversation.id);
        setMessages(messageList.items);
        return;
      }

      const conversation = await api.createConversation(token);
      setConversations([conversation]);
      setActiveConversationId(conversation.id);
      setMessages([]);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete conversation");
    }
  }

  async function handleSendMessage(event: FormEvent) {
    event.preventDefault();
    if (!token || !activeConversationId || !draft.trim()) return;

    setSending(true);
    setError(null);
    try {
      const exchange = await api.sendMessage(token, activeConversationId, draft.trim());
      setMessages((current) => [...current, exchange.user_message, exchange.assistant_message]);
      setDraft("");
      const memoryList = await api.listMemory(token);
      setMemoryItems(memoryList.items);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Unable to send message");
    } finally {
      setSending(false);
    }
  }

  function handleReconnectGoogle() {
    window.location.href = googleAuthReconnectUrl;
  }

  function handleLogout() {
    authStorage.clear();
    setToken(null);
    navigate("/login");
  }

  async function refreshMemory() {
    if (!token) return;
    const memoryList = await api.listMemory(token);
    setMemoryItems(memoryList.items);
  }

  function startEditingMemory(memory: MemoryItem) {
    setEditingMemoryId(memory.id);
    setEditingMemoryContent(memory.content);
  }

  async function handleSaveMemoryEdit(memoryId: string) {
    if (!token || !editingMemoryContent.trim()) return;
    setError(null);
    try {
      await api.correctMemory(token, memoryId, editingMemoryContent.trim());
      setEditingMemoryId(null);
      setEditingMemoryContent("");
      await refreshMemory();
    } catch (editError) {
      setError(editError instanceof Error ? editError.message : "Unable to update memory");
    }
  }

  async function handleForgetMemory(memoryId: string) {
    if (!token) return;
    const confirmed = window.confirm("Forget this memory? The agent will stop using it.");
    if (!confirmed) return;
    setError(null);
    try {
      await api.forgetMemory(token, memoryId);
      await refreshMemory();
    } catch (forgetError) {
      setError(forgetError instanceof Error ? forgetError.message : "Unable to forget memory");
    }
  }

  async function handlePinMemory(memoryId: string) {
    if (!token) return;
    setError(null);
    try {
      await api.pinMemory(token, memoryId);
      await refreshMemory();
    } catch (pinError) {
      setError(pinError instanceof Error ? pinError.message : "Unable to pin memory");
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-gradient-to-br from-white via-brand-50/30 to-white">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
          <p className="text-sm font-medium text-slate-600">Loading your chief of staff...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gradient-to-br from-white via-brand-50/20 to-slate-50">
      <header className="shrink-0 border-b border-slate-200/80 bg-white/90 backdrop-blur-sm">
        <div className="flex items-center justify-between px-5 py-3.5">
          <BrandMark subtitle="Chief of Staff" size="sm" />
          <div className="flex items-center gap-3">
            <span className="hidden text-sm font-medium text-slate-600 sm:inline">
              {user?.full_name ?? user?.email}
            </span>
            <Badge variant={workspace?.is_connected ? "success" : "muted"}>
              {workspace?.is_connected ? "Google connected" : "Google not connected"}
            </Badge>
            {workspace?.needs_reconnect ? (
              <Button variant="secondary" size="sm" onClick={handleReconnectGoogle}>
                Reconnect Calendar
              </Button>
            ) : null}
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 overflow-hidden p-3 lg:grid-cols-[260px_minmax(0,1fr)_280px]">
        <Card className="hidden min-h-0 flex-col overflow-hidden lg:flex" padding="none">
          <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Conversations</h2>
            <Button variant="primary" size="sm" onClick={() => void handleNewConversation()}>
              New
            </Button>
          </div>
          <ul className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <div
                  className={`mb-1 flex items-center gap-1 rounded-xl transition-colors ${
                    activeConversationId === conversation.id
                      ? "bg-brand-50 ring-1 ring-brand-200"
                      : "hover:bg-slate-50"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => void handleSelectConversation(conversation.id)}
                    className={`min-w-0 flex-1 px-3 py-2.5 text-left text-sm ${
                      activeConversationId === conversation.id
                        ? "font-medium text-brand-800"
                        : "text-slate-600"
                    }`}
                  >
                    <span className="block truncate">{conversation.title ?? "Untitled"}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${conversation.title ?? "conversation"}`}
                    onClick={() => void handleDeleteConversation(conversation.id)}
                    className="mr-2 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
                  >
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="flex min-h-0 min-w-0 flex-col overflow-hidden" padding="none">
          <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3 lg:hidden">
            <h2 className="text-sm font-semibold text-slate-900">Chat</h2>
            <div className="flex items-center gap-2">
              {activeConversationId ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleDeleteConversation(activeConversationId)}
                >
                  Delete
                </Button>
              ) : null}
              <Button variant="secondary" size="sm" onClick={() => void handleNewConversation()}>
                New chat
              </Button>
            </div>
          </div>

          <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 ring-1 ring-brand-100">
                  <svg
                    viewBox="0 0 24 24"
                    className="h-7 w-7 text-brand-600"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                    />
                  </svg>
                </div>
                <p className="text-sm font-medium text-slate-700">Start a conversation</p>
                <p className="mt-1 max-w-sm text-sm text-slate-500">
                  Try: <span className="font-medium text-brand-700">I hate 9 AM meetings.</span>
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                      message.role === "user"
                        ? "ml-auto border border-brand-700 bg-brand-500/10 text-slate-800"
                        : "mr-auto border border-slate-200 bg-white text-slate-800"
                    }`}
                  >
                    <p
                      className={`text-[10px] font-semibold uppercase tracking-wider ${
                        message.role === "user" ? "text-brand-800" : "text-brand-600"
                      }`}
                    >
                      {message.role === "user" ? "You" : "Assistant"}
                    </p>
                    <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                  </article>
                ))}
                {sending ? (
                  <div className="mr-auto flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                    <span className="flex gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:-0.3s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:-0.15s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400" />
                    </span>
                    <span className="text-xs text-slate-500">Thinking...</span>
                  </div>
                ) : null}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <form
            onSubmit={(event) => void handleSendMessage(event)}
            className="shrink-0 border-t border-slate-100 bg-white p-4"
          >
            {error ? <p className="mb-2 text-sm text-red-600">{error}</p> : null}
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask your chief of staff..."
                disabled={!activeConversationId || sending}
              />
              <Button type="submit" variant="primary" size="md" disabled={!activeConversationId || sending}>
                {sending ? "..." : "Send"}
              </Button>
            </div>
          </form>
        </Card>

        <Card className="hidden min-h-0 flex-col overflow-hidden lg:flex" padding="none">
          <div className="shrink-0 border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Agent Memory</h2>
            <p className="mt-0.5 text-xs text-slate-500">Preferences and facts learned from chat.</p>
          </div>
          <ul className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-3">
            {memoryItems.length === 0 ? (
              <li className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
                No memories yet.
              </li>
            ) : (
              memoryItems.map((memory) => (
                <li
                  key={memory.id}
                  className="mb-2 rounded-xl border border-brand-100 bg-brand-50/50 p-3 last:mb-0"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="success">{memory.memory_type}</Badge>
                    {memory.pinned_at ? <Badge variant="muted">Pinned</Badge> : null}
                  </div>
                  {editingMemoryId === memory.id ? (
                    <div className="mt-2 space-y-2">
                      <textarea
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800"
                        value={editingMemoryContent}
                        onChange={(event) => setEditingMemoryContent(event.target.value)}
                        rows={3}
                      />
                      <div className="flex gap-2">
                        <Button variant="primary" size="sm" onClick={() => void handleSaveMemoryEdit(memory.id)}>
                          Save
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setEditingMemoryId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="mt-2 text-sm leading-relaxed text-slate-700">{memory.content}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Button variant="ghost" size="sm" onClick={() => startEditingMemory(memory)}>
                          Edit
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => void handlePinMemory(memory.id)}>
                          Pin
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => void handleForgetMemory(memory.id)}>
                          Forget
                        </Button>
                      </div>
                    </>
                  )}
                </li>
              ))
            )}
          </ul>
        </Card>
      </main>
    </div>
  );
}
