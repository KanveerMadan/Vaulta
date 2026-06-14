import { create } from "zustand";

const useFinanceStore = create((set) => ({
  // ── Summary ──────────────────────────────────────────────────────────────
  summary: null,
  summaryLoading: false,
  summaryError: null,
  setSummary: (summary) => set({ summary, summaryError: null }),
  setSummaryLoading: (loading) => set({ summaryLoading: loading }),
  setSummaryError: (error) => set({ summaryError: error, summary: null }),

  // ── Transactions ─────────────────────────────────────────────────────────
  transactions: [],
  transactionsLoading: false,
  transactionsError: null,
  transactionsTotal: 0,
  transactionsPage: 1,
  setTransactions: (transactions, total) =>
    set({ transactions, transactionsTotal: total, transactionsError: null }),
  setTransactionsLoading: (loading) => set({ transactionsLoading: loading }),
  setTransactionsError: (error) =>
    set({ transactionsError: error, transactions: [] }),
  setTransactionsPage: (page) => set({ transactionsPage: page }),

  // ── Category spend (derived from summary.categories) ─────────────────────
  // Kept for SpendChart compatibility — populated from summary on fetch
  categorySpend: [],
  setCategorySpend: (categorySpend) => set({ categorySpend }),

  // ── Chat ─────────────────────────────────────────────────────────────────
  chatMessages: [],
  chatLoading: false,
  setChatMessages: (chatMessages) => set({ chatMessages }),
  addChatMessage: (message) =>
    set((state) => ({ chatMessages: [...state.chatMessages, message] })),
  setChatLoading: (loading) => set({ chatLoading: loading }),

  // ── Reset (e.g. on logout) ────────────────────────────────────────────────
  reset: () =>
    set({
      summary: null,
      summaryLoading: false,
      summaryError: null,
      transactions: [],
      transactionsLoading: false,
      transactionsError: null,
      transactionsTotal: 0,
      transactionsPage: 1,
      categorySpend: [],
      chatMessages: [],
      chatLoading: false,
    }),
}));

export { useFinanceStore };
export default useFinanceStore;