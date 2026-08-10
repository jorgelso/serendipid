import type { ChatMessage } from "@/types/domain";
import Markdown from "@/components/Markdown";
import ChatSourceCards from "./ChatSourceCards";
import type { ChatSourceDisplayMode } from "@/lib/useChatSourceDisplayMode";

export default function ChatMessageBubble({
  message,
  sourceDisplayMode,
}: {
  message: ChatMessage;
  sourceDisplayMode: ChatSourceDisplayMode;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] sm:max-w-[75%] rounded-3xl px-4 py-3 ${
          isUser
            ? "bg-coral text-white rounded-br-md"
            : "bg-surface border border-line rounded-bl-md"
        }`}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
        ) : (
          <Markdown text={message.content} />
        )}
        {!isUser && message.sources.length > 0 && (
          <ChatSourceCards sources={message.sources} mode={sourceDisplayMode} />
        )}
      </div>
    </div>
  );
}
