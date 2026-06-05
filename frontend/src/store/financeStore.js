import { create } from 'zustand'

export const useFinanceStore = create((set) => ({
  // Summary data
  spentThisMonth: 0,
  budgetLeft: 0,
  predictedBalance: 0,

  // Transactions
  transactions: [],
  transactionsLoading: false,

  // Category spending
  categorySpend: [],

  // AI chat
  chatMessages: [],
  chatLoading: false,

  // Actions
  setSummary: (data) => set(data),
  setTransactions: (transactions) => set({ transactions }),
  setTransactionsLoading: (v) => set({ transactionsLoading: v }),
  setCategorySpend: (data) => set({ categorySpend: data }),
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setChatLoading: (v) => set({ chatLoading: v }),
  clearChat: () => set({ chatMessages: [] }),
}))