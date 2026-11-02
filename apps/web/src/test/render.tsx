import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "../App";
import { AppProviders, createQueryClient } from "../app/AppProviders";
import { AppShell } from "../layout/AppShell";

/** Render the app routes at `path`, optionally inside the shell. */
export function renderAt(path: string, { shell = false }: { shell?: boolean } = {}) {
  const routes = shell ? (
    <AppShell username="ana" onLogout={() => undefined}>
      <AppRoutes />
    </AppShell>
  ) : (
    <AppRoutes />
  );
  // A fresh cache per test, without retries, so one test never sees another's data.
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  return render(
    <AppProviders client={client}>
      <MemoryRouter initialEntries={[path]}>{routes}</MemoryRouter>
    </AppProviders>,
  );
}
