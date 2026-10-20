import { useEffect, useState } from "react";
import api from "../lib/api";

/**
 * When the user has sample rows from trying Vaulta out (Phase 8 simulations): say they aren't counted, and clear
 * them in one click. They also go by themselves an hour after they were made (services/samples.py).
 */
export default function SamplesBanner({ count: known, refreshKey = 0, onCleared }) {
  // the home page passes the count it already has (/api/home); elsewhere it's fetched
  const [fetched, setFetched] = useState(0);
  const [cleared, setCleared] = useState(false);
  useEffect(() => {
    if (known !== undefined) return undefined;
    let alive = true;
    api.get("/api/simulations").then((r) => { if (alive) { setFetched(r.data.samples); setCleared(false); } }).catch(() => {});
    return () => { alive = false; };
  }, [refreshKey, known]);
  const count = cleared ? 0 : known ?? fetched;
  if (!count) return null;
  const clear = async () => {
    await api.delete("/api/simulations");
    setCleared(true);
    onCleared?.();
  };
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-warn-tint/60 px-4 py-3 text-sm text-ink">
      <span>
        {count} sample transaction{count === 1 ? "" : "s"} from trying vaulta.in out. They aren't counted anywhere and go by
        themselves within an hour.
      </span>
      <button onClick={clear} className="btn-secondary">Clear samples</button>
    </div>
  );
}
