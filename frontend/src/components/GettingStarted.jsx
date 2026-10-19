import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle, Circle } from "@phosphor-icons/react";
import api from "../lib/api";
import { Ring } from "./CoverageRing";

/**
 * The getting-started checklist (Phase 8). Items tick from what the user has actually done (the server works it out,
 * GET /api/checklist); each undone item links to where it's done. Hide it here; Settings brings it back. Not in the demo.
 */
export default function GettingStarted({ checklist }) {
  // comes with /api/home, so it draws with the rest of the page instead of pushing it down later
  const [hidden, setHidden] = useState(null);
  const data = hidden || checklist;
  if (!data?.available || data.dismissed) return null;
  const hide = async () => setHidden((await api.patch("/api/checklist", { dismissed: true })).data);
  return (
    <section className="rule pt-4" aria-labelledby="getting-started-title" data-testid="getting-started">
      <div className="flex items-center gap-4">
        <Ring percent={data.percent} size={72} stroke={7} ariaLabel="Getting started progress" caption="done" />
        <div className="min-w-0">
          <h2 id="getting-started-title" className="font-display text-lg text-ink">Getting started</h2>
          <p className="text-sm text-ink-2">{data.done === data.total ? "All done. Vaulta is fully set up." : `${data.done} of ${data.total} done`}</p>
        </div>
      </div>
      <ul className="mt-3 divide-y divide-line">
        {data.items.map((item) => (
          <li key={item.id} className="flex items-center gap-2.5 py-2 text-sm">
            {item.done
              ? <CheckCircle size={18} weight="fill" className="text-safe shrink-0" aria-hidden />
              : <Circle size={18} className="text-muted shrink-0" aria-hidden />}
            {item.done
              ? <span className="text-muted line-through decoration-line">{item.title}<span className="sr-only"> (done)</span></span>
              : <Link to={item.link} className="text-ink hover:text-accent-text hover:underline">{item.title}</Link>}
          </li>
        ))}
      </ul>
      <div className="mt-1 flex flex-wrap items-center gap-x-3">
        <Link to="/try" className="text-micro font-medium text-accent-text hover:underline">Try it with samples first</Link>
        <button onClick={hide} className="btn-quiet text-micro text-muted">Hide this list</button>
      </div>
    </section>
  );
}
