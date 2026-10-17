import { useEffect, useState } from "react";
import api from "./api";
import TAXONOMY from "./taxonomy.json";

// The two-level taxonomy (a copy of backend/app/data/taxonomy.json; backend tests keep them identical).
// A transaction's category is a group; its optional subcategory is a taxonomy id or "custom:<uuid>".
export { TAXONOMY };
export const CATEGORIES = [...TAXONOMY.groups.map((g) => g.name), ...TAXONOMY.system_groups.map((g) => g.name)];
const SUBCATEGORIES = Object.fromEntries(TAXONOMY.groups.flatMap((g) => g.subcategories.map((s) => [s.id, { ...s, group: g.name }])));

export const isSubcategory = (value) => Boolean(SUBCATEGORIES[value]) || String(value || "").startsWith("custom:");

/** The display name of a subcategory, including the user's own (from useCategoryTree). */
export function subcategoryName(id, tree) {
  if (!id) return null;
  if (SUBCATEGORIES[id]) return SUBCATEGORIES[id].name;
  for (const g of tree?.groups || []) {
    const s = g.subcategories.find((x) => x.id === id);
    if (s) return s.name;
  }
  return null;
}

/** The value a rule or picker shows for (category, subcategory). */
export const categoryValue = (category, subcategory) => subcategory || category || "";

// The user's taxonomy with their own subcategories, fetched once and shared; refreshCategoryTree() after changes.
let cached = null;
const listeners = new Set();
export function refreshCategoryTree() {
  cached = api.get("/api/categories").then((r) => r.data).catch(() => null);
  cached.then((tree) => listeners.forEach((l) => l(tree)));
  return cached;
}
export function useCategoryTree() {
  const fallback = { groups: TAXONOMY.groups, system_groups: TAXONOMY.system_groups.map((g) => g.name) };
  const [tree, setTree] = useState(fallback);
  useEffect(() => {
    let alive = true;
    const set = (t) => alive && t && setTree(t);
    listeners.add(set);
    (cached || refreshCategoryTree()).then(set);
    return () => { alive = false; listeners.delete(set); };
  }, []);
  return tree;
}

// Same rules as KIND_DIRECTIONS in backend/app/models/transaction.py
export const KINDS = {
  spend: { label: "Spending", directions: ["debit"] },
  income: { label: "Income", directions: ["credit"] },
  transfer: { label: "Own-account transfer", directions: ["debit", "credit"] },
  refund: { label: "Refund", directions: ["credit"] },
  reversal: { label: "Failed / reversed", directions: ["debit", "credit"] },
  lent: { label: "Lent", directions: ["debit"] },
  borrowed: { label: "Borrowed", directions: ["credit"] },
  repayment: { label: "Repayment", directions: ["debit", "credit"] },
};

export const kindsFor = (direction) => Object.entries(KINDS).filter(([, k]) => k.directions.includes(direction));
