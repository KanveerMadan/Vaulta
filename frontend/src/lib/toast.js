import { create } from 'zustand'

let nextId = 1

export const useToasts = create((set) => ({
  items: [],
  push: (t) => set((s) => ({ items: [...s.items.slice(-2), { id: nextId++, ...t }] })),
  dismiss: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}))

/** toast("Saved") or toast({ message, action?: { label, onClick }, tone?: 'neutral' | 'danger' }) */
export const toast = (t) => useToasts.getState().push(typeof t === 'string' ? { message: t } : t)
