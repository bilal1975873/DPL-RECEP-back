import type { Message } from '../types';

interface ChatBubbleProps {
  message: Message;
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isBot = message.type === 'bot';
  const time = new Date(message.timestamp).toLocaleTimeString();

  return (
    <div className={`flex ${isBot ? 'justify-start' : 'justify-end'} items-end gap-2`}>
      {isBot && (
        <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center shadow-md mr-1">
          <span className="text-primary-700 font-bold text-lg">🤖</span>
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-5 py-3 shadow-md transition-all duration-200 animate-fade-in
          ${isBot ? 'bg-primary-50 text-primary-900' : 'bg-primary-700 text-white ml-auto'}
        `}
      >
        <p className="text-base leading-relaxed whitespace-pre-line">{message.content}</p>
        <span className={`block text-xs mt-1 ${isBot ? 'text-primary-400' : 'text-primary-200 text-right'}`}>{time}</span>
      </div>
      {!isBot && (
        <div className="h-8 w-8 rounded-full bg-primary-700 flex items-center justify-center shadow-md ml-1">
          <span className="text-white font-bold text-lg">🧑</span>
        </div>
      )}
    </div>
  );
}