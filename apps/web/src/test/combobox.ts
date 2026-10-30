import { fireEvent, within } from "@testing-library/react";

/** The open list of a Combobox field. */
function listOf(field: HTMLElement): HTMLElement {
  if (field.getAttribute("aria-expanded") !== "true") fireEvent.click(field);
  const list = document.getElementById(field.getAttribute("aria-controls") ?? "");
  if (!list) throw new Error("the combobox list did not open");
  return list;
}

/** Picks an option the way a user does: opens the list and clicks the option by its label. */
export function pick(field: HTMLElement, option: string | RegExp): void {
  fireEvent.click(within(listOf(field)).getByRole("option", { name: option }));
}

/** Like `pick`, waiting for options that are still loading. */
export async function pickWhenLoaded(field: HTMLElement, option: string | RegExp): Promise<void> {
  fireEvent.click(await within(listOf(field)).findByRole("option", { name: option }));
}

/** Labels of the options a Combobox offers (opens the list, then closes it). */
export function optionLabels(field: HTMLElement): string[] {
  const labels = within(listOf(field))
    .queryAllByRole("option")
    .map((o) => o.textContent ?? "");
  fireEvent.keyDown(field, { key: "Escape" });
  return labels;
}
