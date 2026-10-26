// @ts-nocheck
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The help marker (`Hint`) must never live INSIDE a `<label>`: the tooltip
 * bubble text would leak into the control's accessible name, and the button
 * would become interactive content inside the label.
 * The proper placement is beside the label in `<span className="app-field-label">`.
 */

function filesIn(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return filesIn(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

/** Lines where a `<Hint` opens while a `<label` is still open before it. */
function hintsInsideLabel(source: string): number[] {
  const lines: number[] = [];
  for (const match of source.matchAll(/<Hint\b/g)) {
    const before = source.slice(0, match.index);
    const opening = Math.max(...[...before.matchAll(/<label\b/g)].map((m) => m.index ?? -1), -1);
    if (opening > before.lastIndexOf("</label>")) lines.push(before.split("\n").length);
  }
  return lines;
}

describe("Hint is always placed outside <label>", () => {
  it("detects the forbidden case and allows the proper placement", () => {
    expect(hintsInsideLabel('<label htmlFor="a">A <Hint>x</Hint></label>')).toEqual([1]);
    expect(hintsInsideLabel('<span><label htmlFor="a">A</label><Hint>x</Hint></span>')).toEqual([]);
    expect(hintsInsideLabel('<span className="app-field-label"><label htmlFor="a">A</label><Hint>x</Hint></span>')).toEqual([]);
  });

  it("ensures all TSX files in src keep Hint outside <label>", () => {
    const findings = filesIn(join(__dirname, "..")).flatMap((path) =>
      hintsInsideLabel(readFileSync(path, "utf-8")).map((line) => `${path}:${line}`),
    );
    expect(findings).toEqual([]);
  });
});
