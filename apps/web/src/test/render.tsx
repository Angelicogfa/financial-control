import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "../App";
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
  return render(<MemoryRouter initialEntries={[path]}>{routes}</MemoryRouter>);
}
