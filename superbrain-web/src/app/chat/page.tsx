"use client";

import { useEffect, useState } from "react";
import type { ChatMessage, ChatThread } from "@/types/domain";
import ChatThreadSidebar from "@/components/chat/ChatThreadSidebar";
import ChatMessageList from "@/components/chat/ChatMessageList";
import ChatInput from "@/components/chat/ChatInput";
import ChatDisclaimer from "@/components/chat/ChatDisclaimer";
import ChatSourceModeToggle from "@/components/chat/ChatSourceModeToggle";
import { useChatSourceDisplayMode } from "@/lib/useChatSourceDisplayMode";

export default function ChatPage() {
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceDisplayMode, setSourceDisplayMode] = useChatSourceDisplayMode();

  useEffect(() => {
    fetch("/api/chat/threads")
      .then((res) => res.json())
      .then((data) => setThreads(data.data ?? []))
      .catch(() => {});
  }, []);

  async function loadThread(id: string) {
    setActiveThreadId(id);
    setLoadingThread(true);
    setError(null);
    try {
      const res = await fetch(`/api/chat/threads/${id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load that conversation.");
      setMessages(data.data.messages ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load that conversation.");
    } finally {
      setLoadingThread(false);
    }
  }

  async function handleNewThread() {
    setError(null);
    try {
      const res = await fetch("/api/chat/threads", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not start a new conversation.");
      const thread: ChatThread = data.data;
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start a new conversation.");
    }
  }

  async function handleDeleteThread(id: string) {
    try {
      await fetch(`/api/chat/threads/${id}`, { method: "DELETE" });
    } catch {
      // best-effort — still remove locally so the UI doesn't get stuck
    }
    setThreads((prev) => prev.filter((t) => t.id !== id));
    if (activeThreadId === id) {
      setActiveThreadId(null);
      setMessages([]);
    }
  }

  async function handleSend(message: string) {
    setError(null);
    let threadId = activeThreadId;

    if (!threadId) {
      try {
        const res = await fetch("/api/chat/threads", { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Could not start a new conversation.");
        const thread: ChatThread = data.data;
        setThreads((prev) => [thread, ...prev]);
        threadId = thread.id;
        setActiveThreadId(threadId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not start a new conversation.");
        return;
      }
    }

    setSending(true);
    try {
      const res = await fetch(`/api/chat/threads/${threadId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "The chatbot couldn't answer that.");
      const { user_message, assistant_message } = data.data as {
        user_message: ChatMessage;
        assistant_message: ChatMessage;
      };
      setMessages((prev) => [...prev, user_message, assistant_message]);
      setThreads((prev) =>
        [...prev]
          .map((t) =>
            t.id === threadId
              ? { ...t, updated_at: assistant_message.created_at, title: t.title ?? message.slice(0, 80) }
              : t
          )
          .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The chatbot couldn't answer that.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl flex flex-col md:flex-row md:h-[calc(100vh-72px)]">
      <ChatThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={loadThread}
        onNew={handleNewThread}
        onDelete={handleDeleteThread}
      />
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4">
          <h1 className="font-display font-semibold text-2xl">Chat</h1>
          <ChatSourceModeToggle mode={sourceDisplayMode} onChange={setSourceDisplayMode} />
        </div>

        <div className="px-4 pt-3">
          <ChatDisclaimer />
        </div>

        {error && (
          <div className="mx-4 mt-3 rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
            {error}
          </div>
        )}

        {loadingThread ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-ink-muted">Loading…</p>
          </div>
        ) : (
          <ChatMessageList
            messages={messages}
            sending={sending}
            sourceDisplayMode={sourceDisplayMode}
          />
        )}

        <ChatInput onSend={handleSend} disabled={sending} />
      </div>
    </div>
  );
}
