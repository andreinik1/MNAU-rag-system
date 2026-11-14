import React from 'react';

interface ChatInputProps {
  input: string;
  setInput: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  loading: boolean;
}

export default function ChatInput({ input, setInput, onSubmit, loading }: ChatInputProps) {
  return (
    <footer className="bg-white border-t border-slate-200 p-3 sm:p-4 shadow-inner shrink-0">
      <form onSubmit={onSubmit} className="max-w-4xl mx-auto flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Напишіть запитання (наприклад: Як поселитися в гуртожиток?)..."
          className="flex-1 border border-slate-300 rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 focus:outline-none focus:border-emerald-600 text-slate-700 bg-slate-50 text-sm sm:text-base"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-emerald-700 hover:bg-emerald-800 disabled:bg-slate-300 text-white font-semibold px-4 sm:px-6 py-2.5 sm:py-3 rounded-xl transition-colors shadow-sm text-sm sm:text-base shrink-0"
        >
          Надіслати
        </button>
      </form>
    </footer>
  );
}