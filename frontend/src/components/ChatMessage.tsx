import type { Message } from '../types/chat';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full`}>
      <div
        className={`max-w-[85%] sm:max-w-xl md:max-w-2xl rounded-2xl px-4 py-3 shadow-sm text-sm sm:text-base ${isUser
            ? 'bg-emerald-700 text-white rounded-br-none'
            : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none'
          }`}
      >
        {/* Рендерим Markdown вместо обычного текста */}
        <div className="markdown-body leading-relaxed space-y-2">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>

        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-100 text-xs text-slate-500">
            <span className="font-semibold block mb-1">📚 Офіційні джерела:</span>
            <ul className="space-y-1">
              {message.sources.map((src, index) => (
                <li key={index} className="truncate">
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
  );
}