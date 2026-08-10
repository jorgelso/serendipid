"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/domain";
import ChatMessageBubble from "./ChatMessageBubble";
import type { ChatSourceDisplayMode } from "@/lib/useChatSourceDisplayMode";

export default function ChatMessageList({
  messages,
  sending,
  sourceDisplayMode,
}: {
  messages: ChatMessage[];
  sending: boolean;
  sourceDisplayMode: ChatSourceDisplayMode;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, sending]);

  if (messages.length === 0 && !sending) {
    return (
      <div className="flex-1 flex items-center justify-center px-6">
        <p className="text-sm text-ink-muted text-center max-w-sm">
          Ask about anything you&rsquo;ve saved — a topic, a technique, a place — and
          I&rsquo;ll answer from what you&rsquo;ve actually saved, with sources.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
      {messages.map((message) => (
        <ChatMessageBubble
          key={message.id}
          message={message}
          sourceDisplayMode={sourceDisplayMode}
        />
      ))}
      {sending && (
        <div className="flex justify-start">
          <div className="rounded-3xl rounded-bl-md border border-line bg-surface px-4 py-3.5">
            <span className="inline-flex gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-bounce [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-bounce [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 rounded-full bg-ink-muted animate-bounce" />
            </span>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
