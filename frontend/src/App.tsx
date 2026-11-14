import React, { useState, useRef, useEffect } from 'react';

interface Source {
  source_file: string;
  source_url?: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  from_cache?: boolean;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Привіт! Я офіційний віртуальний помічник Миколаївського національного аграрного університету (МНАУ). Чим можу допомогти?',
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userQuestion = input.trim();
    setInput('');
    
    setMessages((prev) => [...prev, { role: 'user', content: userQuestion }]);
    setLoading(true);

    try {
      // Запрос к нашему FastAPI бэкенду
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: userQuestion }),
      });

      if (!response.ok) {
        throw new Error('Помилка сервера при отриманні відповіді');
      }

      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          from_cache: data.from_cache,
        },
      ]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ Вибачте, сталася помилка зʼєднання з сервером. Переконайтеся, що FastAPI бэкенд запущено.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 font-sans">
      {/* Шапка */}
      <header className="bg-emerald-800 text-white shadow-md py-4 px-6 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="bg-white text-emerald-900 font-bold px-3 py-1.5 rounded-lg text-lg shadow">МНАУ</div>
          <div>
            <h1 className="text-lg font-bold">Студентський AI-Помічник</h1>
            <p className="text-xs text-emerald-200">Офіційна база знань університету (RAG + Семантичний кеш)</p>
          </div>
        </div>
      </header>

      {/* Область чата */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 max-w-4xl w-full mx-auto">
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-xl md:max-w-2xl rounded-2xl px-4 py-3 shadow-sm ${
                msg.role === 'user'
                  ? 'bg-emerald-700 text-white rounded-br-none'
                  : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none'
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>

              {/* Источники */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 pt-2 border-t border-slate-100 text-xs text-slate-500">
                  <span className="font-semibold block mb-1">📚 Офіційні джерела:</span>
                  <ul className="space-y-1">
                    {msg.sources.map((src, sIndex) => (
                      <li key={sIndex}>
                        {src.source_url ? (
                          <a
                            href={src.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-emerald-600 hover:underline truncate block"
                          >
                            🔗 {src.source_file}
                          </a>
                        ) : (
                          <span>📄 {src.source_file}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white text-slate-500 border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm flex items-center space-x-2">
              <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce"></div>
              <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce [animation-delay:0.2s]"></div>
              <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce [animation-delay:0.4s]"></div>
              <span className="text-sm ml-2">Шукаю інформацію в базі МНАУ...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Поле ввода */}
      <footer className="bg-white border-t border-slate-200 p-4 shadow-inner">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Напишіть запитання (наприклад: Як поселитися в гуртожиток?)..."
            className="flex-1 border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:border-emerald-600 text-slate-700 bg-slate-50"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-emerald-700 hover:bg-emerald-800 disabled:bg-slate-300 text-white font-semibold px-6 py-3 rounded-xl transition-colors shadow-sm"
          >
            Надіслати
          </button>
        </form>
      </footer>
    </div>
  );
}