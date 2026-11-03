import { render as baseRender, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
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
  return baseRender(
    <AppProviders client={testClient()}>
      <MemoryRouter initialEntries={[path]}>{routes}</MemoryRouter>
    </AppProviders>,
  );
}

/** A fresh cache per test, without retries, so one test never sees another's data. */
function testClient() {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  return client;
}

/** `render` of Testing Library with the data cache the screens read from. */
export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  const client = testClient();
  const wrapper = ({ children }: { children: ReactNode }) => <AppProviders client={client}>{children}</AppProviders>;
  return baseRender(ui, { ...options, wrapper });
}
