/** Data cache shared by every screen (Phase 48.R3, decision 48.0-2): a tab or a page that asks
 *  for data already loaded gets it at once; a newer search cancels the older one. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 },
      mutations: { retry: false },
    },
  });
}

export function AppProviders({ children, client }: Readonly<{ children: ReactNode; client?: QueryClient }>) {
  const [own] = useState(() => client ?? createQueryClient());
  return <QueryClientProvider client={own}>{children}</QueryClientProvider>;
}
