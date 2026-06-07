import { create } from 'zustand'

export const useFinanceStore = create((set) => ({
  summary: null,
  summaryLoading: true,
  transactions: [],
  transactionsLoading: true,
  categorySpend: [],
  chatMessages: [],
  chatLoading: false,

  setSummary: (summary) => set({ summary, summaryLoading: false }),
  setTransactions: (transactions) => set({ transactions, transactionsLoading: false }),
  setCategorySpend: (categorySpend) => set({ categorySpend }),
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setChatLoading: (chatLoading) => set({ chatLoading }),
  clearChat: () => set({ chatMessages: [] }),
}))