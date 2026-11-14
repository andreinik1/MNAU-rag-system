export default function Header() {
  return (
    <header className="bg-emerald-800 text-white shadow-md py-3 px-4 sm:px-6 flex items-center justify-between shrink-0">
      <div className="flex items-center space-x-3">
        <div className="bg-white text-emerald-900 font-bold px-3 py-1.5 rounded-lg text-base sm:text-lg shadow">
          МНАУ
        </div>
        <div>
          <h1 className="text-base sm:text-lg font-bold">Студентський AI-Помічник</h1>
          <p className="text-[11px] sm:text-xs text-emerald-200">Офіційна база знань університету</p>
        </div>
      </div>
    </header>
  );
}