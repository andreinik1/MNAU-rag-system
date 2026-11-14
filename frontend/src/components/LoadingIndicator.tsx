export default function LoadingIndicator() {
  return (
    <div className="flex justify-start w-full">
      <div className="bg-white text-slate-500 border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm flex items-center space-x-2">
        <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce"></div>
        <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce [animation-delay:0.2s]"></div>
        <div className="w-2 h-2 bg-emerald-600 rounded-full animate-bounce [animation-delay:0.4s]"></div>
        <span className="text-xs sm:text-sm ml-2">Шукаю інформацію в базі МНАУ...</span>
      </div>
    </div>
  );
}