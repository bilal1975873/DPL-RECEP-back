import React from 'react';
import { ChatBubble } from './ChatBubble';
import { ChatInput } from './ChatInput';
import type { Message } from '../types';

interface ChatContainerProps {
  messages: Message[];
  isLoading: boolean;
  onSend: (message: string) => void;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  messages,
  isLoading,
  onSend,
}) => {
  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const chatContainerRef = React.useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = React.useState(true);

  const scrollToBottom = React.useCallback(() => {
    if (shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [shouldAutoScroll]);

  const handleScroll = () => {
    const container = chatContainerRef.current;
    if (container) {
      const isAtBottom =
        container.scrollHeight - container.scrollTop <= container.clientHeight + 100;
      setShouldAutoScroll(isAtBottom);
    }
  };

  React.useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  return (
    <div className="flex flex-col h-full min-h-0 w-full max-w-4xl mx-auto">
      <div
        ref={chatContainerRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4 space-y-4 glass-effect rounded-t-2xl"
      >
        {messages.map((message, index) => (
          <ChatBubble
            key={index}
            message={message}
            className={`message-animate delay-${index % 5}`}
            onSelect={onSend}
          />
        ))}
        {isLoading && (
          <div className="flex items-center space-x-2 text-red-500 opacity-75 loading-pulse">
            <div className="w-2 h-2 rounded-full bg-current"></div>
            <div className="w-2 h-2 rounded-full bg-current"></div>
            <div className="w-2 h-2 rounded-full bg-current"></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <ChatInput onSend={onSend} isLoading={isLoading} />
    </div>
  );
};