import { useState } from 'react';
import type { FormEvent } from 'react';
import { PaperAirplaneIcon } from '@heroicons/react/24/solid';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex space-x-2">
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Type your message..."
        className="input-field text-base bg-white/80 focus:bg-white"
        disabled={disabled}
        autoFocus
        autoComplete="off"
        maxLength={300}
      />
      <button
        type="submit"
        disabled={!message.trim() || disabled}
        className="btn-primary flex items-center justify-center px-5 py-2 text-lg"
        aria-label="Send message"
      >
        <PaperAirplaneIcon className="h-5 w-5" />
      </button>
    </form>
  );
}