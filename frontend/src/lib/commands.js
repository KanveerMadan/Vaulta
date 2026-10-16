import { create } from 'zustand'

/** Open state of the command palette (⌘K / Ctrl+K). */
export const useCommandPalette = create((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
}))
