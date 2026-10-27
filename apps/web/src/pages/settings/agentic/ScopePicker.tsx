import { useMemo, useState } from "react";

import type { GrantableContextDTO, GrantableOperationDTO } from "../../../api/types";
import { ChevronDownIcon, ChevronRightIcon } from "../../../layout/icons";
import type { Scope } from "./scope";

const READ_ONLY_KINDS = new Set<GrantableOperationDTO["kind"]>(["query"]);

const MODULE_LABELS: Record<string, string> = {
  portfolio: "Carteira e desempenho",
  assets: "Ativos",
  contributions: "Aportes",
  ledger: "Lançamentos",
  research: "Pesquisa B3",
  policy: "Estratégia",
  accounts: "Contas",
  alerts: "Alertas",
  market: "Dados de mercado",
};

const KIND_LABELS: Record<GrantableOperationDTO["kind"], string> = {
  query: "Consulta",
  command: "Comando",
};

function domKeyOf(name: string): string {
  return name.replaceAll(".", "_");
}

function moduleOf(contextName: string): string {
  return contextName.split(".")[0];
}

function verbOf(operationName: string): string {
  return operationName.slice(operationName.lastIndexOf(".") + 1);
}

/**
 * Interactive scope selector grouping grantable contexts and operations by module.
 * Clicking the context header expands its individual operations; checking "Contexto inteiro"
 * grants the entire context (including future operations in that context).
 */
export function ScopePicker({
  contexts,
  value,
  onChange,
}: Readonly<{
  contexts: GrantableContextDTO[];
  value: Scope;
  onChange: (next: Scope) => void;
}>) {
  const [filterText, setFilterText] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const query = filterText.trim().toLowerCase();

  const visibleItems = useMemo(() => {
    return contexts
      .map((context) => {
        const ops = context.operations;
        if (!query) return { context, ops };
        const matchesContext =
          context.name.toLowerCase().includes(query) ||
          context.label.toLowerCase().includes(query);
        const matchingOps = ops.filter(
          (op) =>
            op.name.toLowerCase().includes(query) ||
            op.description.toLowerCase().includes(query),
        );
        return { context, ops: matchesContext ? ops : matchingOps };
      })
      .filter(({ ops }) => ops.length > 0);
  }, [contexts, query]);

  const byModule = useMemo(() => {
    const groups = new Map<string, typeof visibleItems>();
    for (const item of visibleItems) {
      const mod = moduleOf(item.context.name);
      groups.set(mod, [...(groups.get(mod) ?? []), item]);
    }
    return [...groups.entries()];
  }, [visibleItems]);

  const wholeSet = new Set(value.contexts);
  const singleSet = new Set(value.operations);

  function toggleExpanded(contextName: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(contextName)) next.delete(contextName);
      else next.add(contextName);
      return next;
    });
  }

  function toggleWholeContext(context: GrantableContextDTO) {
    if (wholeSet.has(context.name)) {
      onChange({ ...value, contexts: value.contexts.filter((c) => c !== context.name) });
      return;
    }
    const childNames = new Set(context.operations.map((op) => op.name));
    onChange({
      contexts: [...value.contexts, context.name],
      operations: value.operations.filter((op) => !childNames.has(op)),
    });
  }

  function toggleOperation(operationName: string) {
    onChange({
      ...value,
      operations: singleSet.has(operationName)
        ? value.operations.filter((op) => op !== operationName)
        : [...value.operations, operationName],
    });
  }

  function setContextOperations(context: GrantableContextDTO, selectedOps: string[]) {
    const childNames = new Set(context.operations.map((op) => op.name));
    onChange({
      contexts: value.contexts.filter((c) => c !== context.name),
      operations: [...value.operations.filter((op) => !childNames.has(op)), ...selectedOps],
    });
  }

  function selectReadOnlyEverywhere() {
    const queries = contexts.flatMap((c) =>
      c.operations.filter((op) => op.grantable && READ_ONLY_KINDS.has(op.kind)).map((op) => op.name),
    );
    onChange({ contexts: [], operations: queries });
  }

  function selectEverythingGrantable() {
    const allOps = contexts.flatMap((c) =>
      c.operations.filter((op) => op.grantable).map((op) => op.name),
    );
    onChange({ contexts: [], operations: allOps });
  }

  return (
    <div className="app-scope">
      <div className="app-scope-toolbar">
        <input
          type="search"
          className="app-scope-filter"
          placeholder="Filtrar por módulo, operação ou descrição…"
          aria-label="Filtrar operações"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
        />
        <div className="app-scope-shortcuts">
          <button type="button" className="app-link-button" onClick={selectEverythingGrantable}>
            Conceder todas as operações
          </button>
          <button type="button" className="app-link-button" onClick={selectReadOnlyEverywhere}>
            Somente leitura em tudo
          </button>
          <button
            type="button"
            className="app-link-button"
            onClick={() => onChange({ contexts: [], operations: [] })}
          >
            Limpar seleção
          </button>
        </div>
      </div>

      {byModule.length === 0 && (
        <p className="app-muted">Nenhuma operação encontrada para esse filtro.</p>
      )}

      {byModule.map(([mod, items]) => (
        <section key={mod} className="app-scope-module">
          <h3 className="app-scope-module-title">{MODULE_LABELS[mod] ?? mod}</h3>

          {items.map(({ context, ops }) => {
            const isWhole = wholeSet.has(context.name);
            const isOpen = expanded.has(context.name) || Boolean(query);
            const selectedCount = isWhole
              ? context.operations.length
              : context.operations.filter((op) => singleSet.has(op.name)).length;
            const opsContainerId = `scope-ops-${domKeyOf(context.name)}`;

            return (
              <div
                key={context.name}
                className={`app-scope-context${isWhole ? " is-whole" : ""}`}
              >
                <div className="app-scope-context-head">
                  <button
                    type="button"
                    className="app-scope-context-toggle"
                    aria-expanded={isOpen}
                    aria-controls={opsContainerId}
                    onClick={() => toggleExpanded(context.name)}
                  >
                    {isOpen ? (
                      <ChevronDownIcon width={14} height={14} aria-hidden="true" />
                    ) : (
                      <ChevronRightIcon width={14} height={14} aria-hidden="true" />
                    )}
                    <span className="app-scope-context-label">{context.label}</span>
                    <code className="app-scope-context-code">{context.name}</code>
                    <span className={`app-badge${selectedCount > 0 ? " app-badge-success" : ""}`}>
                      {selectedCount}/{context.operations.length}
                    </span>
                  </button>

                  <label className="app-check app-scope-whole">
                    <input
                      type="checkbox"
                      checked={isWhole}
                      onChange={() => toggleWholeContext(context)}
                      aria-label={`Conceder contexto inteiro ${context.name}`}
                    />
                    Contexto inteiro
                  </label>
                </div>

                {isOpen && (
                  <div id={opsContainerId} className="app-scope-operations">
                    {!isWhole && (
                      <div className="app-button-row app-scope-quick">
                        <button
                          type="button"
                          className="app-link-button"
                          onClick={() =>
                            setContextOperations(
                              context,
                              context.operations
                                .filter((op) => op.grantable && READ_ONLY_KINDS.has(op.kind))
                                .map((op) => op.name),
                            )
                          }
                        >
                          Só leitura
                        </button>
                        <button
                          type="button"
                          className="app-link-button"
                          onClick={() =>
                            setContextOperations(
                              context,
                              context.operations.filter((op) => op.grantable).map((op) => op.name),
                            )
                          }
                        >
                          Todas deste contexto
                        </button>
                        <button
                          type="button"
                          className="app-link-button"
                          onClick={() => setContextOperations(context, [])}
                        >
                          Nenhuma
                        </button>
                      </div>
                    )}
                    {isWhole && (
                      <p className="app-muted app-scope-whole-note">
                        O contexto inteiro está concedido: inclui todas as operações atuais e futuras de{" "}
                        <code>{context.name}</code>.
                      </p>
                    )}

                    {ops.map((operation) => (
                      <label key={operation.name} className="app-scope-operation">
                        <input
                          type="checkbox"
                          checked={isWhole || singleSet.has(operation.name)}
                          disabled={isWhole}
                          onChange={() => toggleOperation(operation.name)}
                          aria-label={operation.name}
                        />
                        <span className="app-scope-operation-main">
                          <span className="app-scope-operation-head">
                            <code>{verbOf(operation.name)}</code>
                            <span className={`app-badge app-scope-kind-${operation.kind}`}>
                              {KIND_LABELS[operation.kind]}
                            </span>
                          </span>
                          <span className="app-muted app-scope-operation-desc">
                            {operation.description}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
