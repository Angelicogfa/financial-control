import { useCallback, useEffect, useRef, useState } from "react";

export interface ApiState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** Load again (after a change, or on "Tentar de novo"). */
  reload: () => void;
}

/**
 * Load data for a screen. `key` names what is being loaded: when it changes (a new id, a
 * new filter) the data loads again. The loader always sees the latest props.
 */
export function useApi<T>(key: string, load: () => Promise<T>): ApiState<T> {
  const loader = useRef(load);
  loader.current = load;
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    loader
      .current()
      .then((data) => {
        if (active) setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (active) setState({ data: null, error, loading: false });
      });
    return () => {
      active = false;
    };
  }, [key, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}
