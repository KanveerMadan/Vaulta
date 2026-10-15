import { useEffect, useState } from "react";
import api from "./api";

export const rupees = (v) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const shortDay = (iso) =>
  new Date(`${String(iso).slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/** GET `url` whenever `refreshKey` changes. Returns {data, error}. */
export function useApi(url, refreshKey) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    api.get(url)
      .then((res) => alive && setState({ data: res.data, error: null }))
      .catch(() => alive && setState((s) => ({ ...s, error: "Couldn't load this. Try again in a moment." })));
    return () => { alive = false; };
  }, [url, refreshKey]);
  return state;
}
