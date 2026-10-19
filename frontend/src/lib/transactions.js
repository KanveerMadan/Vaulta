import api from "./api";

/** POST a manual entry. client_id makes a double-submit return the same transaction. */
export async function addManualTransaction(entry) {
  const { data } = await api.post("/api/transactions", { client_id: crypto.randomUUID(), ...entry });
  return data;
}

/** PATCH category and/or notes. category null clears it. */
export async function updateTransaction(id, changes) {
  const { data } = await api.patch(`/api/transactions/${id}`, changes);
  return data;
}

/** DELETE — the server allows it for manual entries only. */
export async function deleteTransaction(id) {
  await api.delete(`/api/transactions/${id}`);
}
