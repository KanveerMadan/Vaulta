import { useState } from "react";
import api from "../lib/api";
import { useApi } from "../lib/format";

function Toggle({ checked, onChange, label, disabled }) {
  return (
    <label className={`flex items-center gap-2 text-sm ${disabled ? "opacity-50" : ""}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/** Link a Telegram chat with a one-time code (Settings and onboarding). */
export default function TelegramLink() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data } = useApi("/api/telegram", refreshKey);
  const [code, setCode] = useState(null);
  const reload = () => setRefreshKey((k) => k + 1);
  if (!data || !data.configured) return null;

  const getCode = async () => setCode((await api.post("/api/telegram/link-code")).data);
  const unlink = async () => { await api.delete("/api/telegram", { recent: true }); setCode(null); reload(); };
  const setWeekly = async (weekly) => { await api.patch("/api/telegram", { weekly }); reload(); };

  return (
    <section id="telegram" className="card p-5 space-y-3 scroll-mt-20">
      <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-widest">Telegram</h2>
      <p className="text-xs text-ink-500">
        Log expenses and ask questions from Telegram. Messages you send to the bot pass through Telegram.
        Bill photos are never read there; use Scan bill in the app so the photo stays on your phone.
      </p>
      {data.linked ? (
        <>
          <p className="text-sm text-safe">✓ Linked{data.bot_username ? ` to @${data.bot_username}` : ""}</p>
          <Toggle checked={data.weekly} onChange={setWeekly} label="Also send my weekly report summary on Telegram" />
          <button onClick={unlink} className="text-xs text-ink-400 hover:text-danger">Unlink Telegram</button>
        </>
      ) : code ? (
        <div className="text-sm space-y-2">
          {data.bot_username && (
            <a href={`https://t.me/${data.bot_username}?start=${code.code}`} target="_blank" rel="noopener noreferrer"
              className="inline-block btn-primary text-sm py-1.5 px-3">Open @{data.bot_username} and link</a>
          )}
          <p className="text-ink-700">Or send <code>/start {code.code}</code> to the bot. The code works once, for 10 minutes.</p>
          <button onClick={reload} className="text-xs text-forest-600">I've sent it</button>
        </div>
      ) : (
        <button onClick={getCode} className="btn-primary-light text-sm py-1.5 px-3">Link Telegram</button>
      )}
    </section>
  );
}
