import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigationType, useSearchParams } from "react-router-dom";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { MagnifyingGlass, Receipt } from "@phosphor-icons/react";
import api from "../lib/api";
import { isSubcategory } from "../lib/categories";
import { useApi } from "../lib/format";
import CategorySelect from "../components/CategorySelect";
import { ruleToast } from "../lib/ruleToast";
import TransactionRow from "../components/TransactionRow";
import SamplesBanner from "../components/SamplesBanner";
import Empty from "../ui/Empty";
import { SkeletonRows } from "../ui/Skeleton";

const PAGE = 200;
const ROW_ESTIMATE = 66;

function useTransactions(search, category, tag, reloadKey) {
  const [state, setState] = useState({ items: [], total: 0, page: 0, hasMore: true, loading: true, error: null });
  const [page, setPage] = useState(1);
  const key = `${search}|${category}|${tag}|${reloadKey}`;
  const [shownKey, setShownKey] = useState(key);
  if (shownKey !== key) { setShownKey(key); setPage(1); }   // new filters start again from page 1

  useEffect(() => {
    let alive = true;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE) });
    if (search) params.set("merchant", search);
    if (category) params.set(isSubcategory(category) ? "subcategory" : "category", category);
    if (tag) params.set("tag", tag);
    api.get(`/api/transactions?${params}`)
      .then(({ data }) => alive && setState((s) => ({
        items: page === 1 ? data.items : [...s.items, ...data.items], total: data.total, page, hasMore: data.has_more, loading: false, error: null,
      })))
      .catch(() => alive && setState((s) => ({ ...s, loading: false, error: "Couldn't load transactions. Check your connection and try again." })));
    return () => { alive = false; };
  }, [search, category, tag, reloadKey, page]);

  const more = () => { if (state.hasMore && state.page === page) setPage(page + 1); };
  return { ...state, more };
}

export default function Transactions() {
  const [params, setParams] = useSearchParams();
  const search = params.get("q") || "";
  const category = params.get("category") || "";
  const tag = params.get("tag") || "";
  const [draft, setDraft] = useState(search);
  const [reloadKey, setReloadKey] = useState(0);
  const { items, total, hasMore, loading, error, more } = useTransactions(search, category, tag, reloadKey);
  const tags = useApi("/api/tags", reloadKey).data?.items || [];
  const filtered = Boolean(search || category || tag);
  const [sel, setSel] = useState(-1);
  const searchRef = useRef(null);
  const [listTop, setListTop] = useState(0);
  const measureList = (el) => { if (el && el.offsetTop !== listTop) setListTop(el.offsetTop); };
  const rowRefs = useRef(new Map());

  // the search box updates the URL a moment after typing stops
  useEffect(() => {
    const id = setTimeout(() => {
      if (draft === search) return;
      const next = new URLSearchParams(params);
      if (draft) next.set("q", draft); else next.delete("q");
      setParams(next, { replace: true });
    }, 250);
    return () => clearTimeout(id);
  }, [draft, search, params, setParams]);

  const virtualizer = useWindowVirtualizer({
    count: items.length,
    getItemKey: (i) => items[i].id,          // measured heights follow the transaction, not its position in the list
    estimateSize: () => ROW_ESTIMATE,
    overscan: 8,
    scrollMargin: listTop,
  });
  // A list opened afresh starts at its top, set through the virtualizer so its own idea of the position agrees with the
  // window's: it starts from the previous page's position, and in WebKit it went on compensating against that as rows
  // were measured, which left a newly opened list at its middle. Back/forward keep their place.
  const navType = useNavigationType();
  useLayoutEffect(() => { if (navType !== "POP") virtualizer.scrollToOffset(0); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const virtual = virtualizer.getVirtualItems();
  const lastIndex = virtual.length ? virtual[virtual.length - 1].index : 0;
  useEffect(() => { if (lastIndex >= items.length - 20) more(); }, [lastIndex, items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // j / k move, e edits the category, / searches, Escape clears
  useEffect(() => {
    const onKey = (e) => {
      const typing = e.target.closest?.("input, textarea, select");
      if (e.key === "/" && !typing) { e.preventDefault(); searchRef.current?.focus(); return; }
      if (e.key === "Escape" && e.target === searchRef.current) { searchRef.current.blur(); return; }
      if (typing || e.metaKey || e.ctrlKey || e.altKey || !items.length) return;
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        setSel((s) => {
          const next = Math.max(0, Math.min(items.length - 1, s + (e.key === "j" ? 1 : -1)));
          virtualizer.scrollToIndex(next, { align: "auto" });
          return next;
        });
      } else if (e.key === "e" && sel >= 0) {
        e.preventDefault();
        rowRefs.current.get(items[sel]?.id)?.editCategory();
      } else if (e.key === "Escape") setSel(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, sel, virtualizer]);

  const setFilter = (name, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-display-s text-ink">Transactions</h1>
          <p className="text-sm text-muted mt-1"><span className="num">{total.toLocaleString("en-IN")}</span> {filtered ? "matching" : "in total"}</p>
        </div>
        <p className="hidden pointer-fine:block text-micro text-muted">
          <kbd className="kbd">/</kbd> search <kbd className="kbd">j</kbd><kbd className="kbd">k</kbd> move <kbd className="kbd">e</kbd> edit category
        </p>
      </header>

      <SamplesBanner refreshKey={reloadKey} onCleared={() => setReloadKey((k) => k + 1)} />

      <div className="flex flex-col sm:flex-row gap-2">
        <label className="relative flex-1">
          <span className="sr-only">Search merchants</span>
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input ref={searchRef} value={draft} onChange={(e) => setDraft(e.target.value)} type="search" spellCheck={false}
            placeholder="Search merchants…" className="input pl-9" />
        </label>
        <CategorySelect value={category} onChange={(v) => setFilter("category", v)} empty="All categories"
          groupOption={(g) => `All ${g}`} aria-label="Category" className="input sm:w-56" />
        {(tags.length > 0 || tag) && (
          <select value={tag} onChange={(e) => setFilter("tag", e.target.value)} aria-label="Tag" className="input sm:w-44">
            <option value="">All tags</option>
            {tag && !tags.some((t) => t.name.toLowerCase() === tag.toLowerCase()) && <option value={tag}>{tag}</option>}
            {tags.map((t) => <option key={t.id} value={t.name}>{t.name} ({t.count})</option>)}
          </select>
        )}
      </div>

      {error ? (
        <div className="rounded-md border border-danger/30 bg-danger-tint p-4 flex items-center justify-between gap-3">
          <p className="text-sm">{error}</p>
          <button onClick={() => setReloadKey((k) => k + 1)} className="btn-secondary">Try again</button>
        </div>
      ) : loading && !items.length ? <SkeletonRows rows={8} /> : !items.length ? (
        <Empty icon={Receipt} title={filtered ? "No matches" : "No transactions yet"} to={filtered ? undefined : "/connect"} cta="Import a statement">
          {filtered ? "Try another merchant name, category or tag." : "Import a statement, forward bank alerts or add one by hand."}
        </Empty>
      ) : (
        <div ref={measureList} role="list" aria-label="Transactions">
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtual.map((v) => {
              const t = items[v.index];
              return (
                <div key={t.id} role="listitem" data-index={v.index} ref={virtualizer.measureElement} onClick={() => setSel(v.index)}
                  className="absolute left-0 right-0 border-b border-line" style={{ transform: `translateY(${v.start - listTop}px)` }}>
                  <TransactionRow ref={(r) => { if (r) rowRefs.current.set(t.id, r); else rowRefs.current.delete(t.id); }}
                    txn={t} selected={v.index === sel} onChanged={() => {}} onTag={(name) => setFilter("tag", name)} onRuleLearned={(rule) => ruleToast(rule, () => setReloadKey((k) => k + 1))} />
                </div>
              );
            })}
          </div>
          {hasMore && <p className="py-4 text-center text-sm text-muted">Loading more…</p>}
        </div>
      )}
    </div>
  );
}
