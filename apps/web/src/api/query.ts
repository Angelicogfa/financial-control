/** Data of a screen from the shared cache (Phase 48.R9, replaces `useApi`).
 *
 *  `key` names what is loaded: when it changes (a new id, a new filter) the data loads again,
 *  and two screens that ask for the same key share one request and one answer. A screen opens
 *  with what is already in the cache and refreshes it on mount (stale at once), so a change
 *  made elsewhere is never hidden; it keeps the previous data while a new key loads. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useRef } from "react";

export interface ApiState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** Load again (after a change, or on "Tentar de novo"). */
  reload: () => void;
}

export function screenKey(key: string): readonly unknown[] {
  return ["screen", key];
}

export function useScreenData<T>(key: string, load: () => Promise<T>): ApiState<T> {
  const loader = useRef(load);
  loader.current = load;
  const query = useQuery({
    queryKey: screenKey(key),
    queryFn: () => loader.current(),
    staleTime: 0,
    retry: false,
    placeholderData: keepPreviousData,
  });
  const { refetch } = query;
  const reload = useCallback(() => void refetch(), [refetch]);
  return {
    data: query.data ?? null,
    error: query.error ?? null,
    loading: query.isFetching,
    reload,
  };
}
