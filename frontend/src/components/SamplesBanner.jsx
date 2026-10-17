import { useEffect, useState } from "react";
import api from "../lib/api";

/**
 * When the user has sample rows from trying Vaulta out (Phase 8 simulations): say they aren't counted, and clear
 * them in one click. They also go by themselves an hour after they were made (services/samples.py).
 */
export default function SamplesBanner({ refreshKey = 0, onCleared }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    api.get("/api/simulations").then((r) => alive && setCount(r.data.samples)).catch(() => {});
    return () => { alive = false; };
  }, [refreshKey]);
  if (!count) return null;
  const clear = async () => {
    await api.delete("/api/simulations");
    setCount(0);
    onCleared?.();
  };
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-warn-tint/60 px-4 py-3 text-sm text-ink">
      <span>
        {count} sample transaction{count === 1 ? "" : "s"} from trying Vaulta out. They aren't counted anywhere and go by
        themselves within an hour.
      </span>
      <button onClick={clear} className="btn-secondary">Clear samples</button>
    </div>
  );
}
