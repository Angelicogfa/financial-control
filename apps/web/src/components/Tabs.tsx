import { useSearchParams } from "react-router-dom";

export interface TabSpec<K extends string> {
  key: K;
  label: string;
}

/** The active tab lives in `?tab=` so links and "back" keep it. */
export function useTab<K extends string>(tabs: TabSpec<K>[], fallback: K): [K, (key: K) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const active = (tabs.some((t) => t.key === raw) ? raw : fallback) as K;
  const select = (key: K) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (key === fallback) next.delete("tab");
        else next.set("tab", key);
        return next;
      },
      { replace: true },
    );
  return [active, select];
}

export function Tabs<K extends string>({
  tabs,
  active,
  onSelect,
  label,
}: Readonly<{ tabs: TabSpec<K>[]; active: K; onSelect: (key: K) => void; label: string }>) {
  return (
    <div className="app-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          className="app-tab"
          onClick={() => onSelect(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
