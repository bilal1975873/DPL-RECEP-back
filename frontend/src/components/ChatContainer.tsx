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
  const chatContainerRef = React.useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = React.useState(true);
  const [isScrolling, setIsScrolling] = React.useState(false);

  const scrollToBottom = React.useCallback(() => {
    if (shouldAutoScroll && !isScrolling && chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [shouldAutoScroll, isScrolling]);

  const handleScroll = () => {
    const container = chatContainerRef.current;
    if (container) {
      setIsScrolling(true);
      const isAtBottom =
        Math.abs(
          container.scrollHeight - container.scrollTop - container.clientHeight
        ) < 10;
      setShouldAutoScroll(isAtBottom);
      setTimeout(() => setIsScrolling(false), 150);
    }
  };

  React.useEffect(() => {
    setTimeout(scrollToBottom, 100);
  }, [messages, scrollToBottom]);

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto" style={{ height: 'calc(100vh - 180px)' }}>
      <div
        ref={chatContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar p-4 space-y-4 glass-effect rounded-t-2xl"
        style={{ maxHeight: 'calc(100vh - 240px)' }}
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
      </div>
      <div className="mt-4 sticky bottom-0 bg-transparent">
        <ChatInput onSend={onSend} isLoading={isLoading} />
      </div>
    </div>
  );
};