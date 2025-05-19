import { useEffect, useRef } from 'react';
import { ChatBubble } from './ChatBubble';
import { ChatInput } from './ChatInput';
import type { Message } from '../types';

interface ChatContainerProps {
  messages: Message[];
  onSend: (message: string) => void;
  isLoading: boolean;
  currentStep?: string;
}

export function ChatContainer({ messages, onSend, isLoading, currentStep }: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (    <div 
      className="flex flex-col h-[500px] md:h-[600px] bg-white/70 rounded-2xl shadow-inner border border-primary-100"
      onClick={() => currentStep === 'complete' && onSend('')}
      style={{ cursor: currentStep === 'complete' ? 'pointer' : 'default' }}
    >
      <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
        {messages.map((message, index) => (
          <ChatBubble key={index} message={message} />
        ))}
        {isLoading && (
          <div className="flex items-center space-x-2 text-primary-700 animate-pulse mt-2">
            <div className="w-2 h-2 bg-primary-700 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-2 h-2 bg-primary-700 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-2 h-2 bg-primary-700 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            <span className="text-sm font-medium">AI is thinking...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="border-t border-primary-100 p-4 bg-white/80">
        <ChatInput onSend={onSend} disabled={isLoading} />
      </div>
    </div>
  );
}