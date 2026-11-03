import type { GrantableContextDTO } from "../../../api/types";

/** Selected grant scope: whole contexts plus individual operation names. */
export interface Scope {
  contexts: string[];
  operations: string[];
}

/** Counts how many distinct operations are reached by the selected scope. */
export function scopeSize(contexts: GrantableContextDTO[], value: Scope): number {
  const wholeContexts = new Set(value.contexts);
  const reached = new Set(value.operations);
  for (const context of contexts) {
    if (wholeContexts.has(context.name)) {
      context.operations.forEach((op) => reached.add(op.name));
    }
  }
  return reached.size;
}
