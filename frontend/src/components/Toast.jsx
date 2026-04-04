import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)

let nextId = 0

const ICONS = {
  error: (
    <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
    </svg>
  ),
  warning: (
    <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
    </svg>
  ),
  success: (
    <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
    </svg>
  ),
  info: (
    <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clipRule="evenodd" />
    </svg>
  ),
}

const STYLES = {
  error: 'bg-accent-error/15 border-accent-error/40 text-accent-error',
  warning: 'bg-accent-warning/15 border-accent-warning/40 text-accent-warning',
  success: 'bg-accent-success/15 border-accent-success/40 text-accent-success',
  info: 'bg-accent-info/15 border-accent-info/40 text-accent-info',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef({})

  const removeToast = useCallback((id) => {
    clearTimeout(timersRef.current[id])
    delete timersRef.current[id]
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const addToast = useCallback((message, type = 'error', duration = 5000) => {
    const id = ++nextId
    setToasts(prev => [...prev.slice(-4), { id, message, type }])
    if (duration > 0) {
      timersRef.current[id] = setTimeout(() => removeToast(id), duration)
    }
    return id
  }, [removeToast])

  const toast = useMemo(() => ({
    error: (msg, dur) => addToast(msg, 'error', dur ?? 6000),
    warning: (msg, dur) => addToast(msg, 'warning', dur ?? 5000),
    success: (msg, dur) => addToast(msg, 'success', dur ?? 4000),
    info: (msg, dur) => addToast(msg, 'info', dur ?? 4000),
  }), [addToast])

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Toast container — fixed bottom-right */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`flex items-start gap-2 px-4 py-3 rounded-lg border text-sm animate-fade-in ${STYLES[t.type] || STYLES.error}`}
          >
            {ICONS[t.type]}
            <span className="flex-1 break-words">{t.message}</span>
            <button
              onClick={() => removeToast(t.id)}
              className="opacity-60 hover:opacity-100 text-xs shrink-0 ml-1"
            >
              x
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
