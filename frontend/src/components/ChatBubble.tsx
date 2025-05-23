import React from 'react';
import type { Message } from '../types';

interface ChatBubbleProps {
  message: Message;
  className?: string;
  onSelect?: (text: string) => void;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({ message, className = '', onSelect }) => {
  const isBot = message.type === 'bot';
  // Extract numbered options and main prompt
  const lines = message.content.split('\n');
  const options = lines.filter(line => line.match(/^\d+\./));
  const prompt = lines.filter(line => !line.match(/^\d+\./) && line.trim() !== '').join(' ');
  const showButtons = isBot && options.length > 0;

  return (
    <div className={`flex ${isBot ? 'justify-start' : 'justify-end'} ${className}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isBot
            ? 'bg-gradient-to-br from-gray-800 to-gray-900 text-white mr-auto chat-shadow'
            : 'bg-gradient-to-br from-red-600 to-red-700 text-white ml-auto glow-effect'
        }`}
      >
        {/* Show prompt as heading if there are options, else show full message */}
        {showButtons ? (
          <>
            <div className="font-semibold text-base md:text-lg mb-2">{prompt}</div>
            <div className="flex flex-col gap-3 mt-2">
              {options.map((option, index) => {
                // Extract the number (e.g., '2') from '2. I am a vendor'
                const match = option.match(/^(\d+)\./);
                const valueToSend = match ? match[1] : option;
                return (
                  <button
                    key={index}
                    onClick={() => onSelect?.(valueToSend)}
                    className="w-full text-left px-5 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl font-medium text-base shadow-lg hover:shadow-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-400"
                  >
                    {option.replace(/^\d+\.\s*/, '')}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <p className="text-sm md:text-base whitespace-pre-wrap">{message.content}</p>
        )}
        <span className="text-xs opacity-50 mt-3 block text-right">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
};