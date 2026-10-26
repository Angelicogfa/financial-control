import { useEffect, useId, useState, type CSSProperties, type ReactNode } from "react";

/**
 * Informative tooltip that does not occupy space in the layout.
 *
 * Replacing helper text below input fields prevents form shifts and height discrepancies.
 * The hint marker stays beside the <label> (inside <span className="app-field-label">)
 * rather than inside <label>, ensuring the hint bubble doesn't become part of the
 * accessible name of the input control.
 */

const VISUALLY_HIDDEN: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

const BUBBLE: CSSProperties = {
  position: "absolute",
  top: "calc(100% + 6px)",
  left: 0,
  zIndex: 30,
  width: "max-content",
  maxWidth: 280,
  padding: "7px 10px",
  borderRadius: "var(--app-radius-sm, 6px)",
  background: "var(--app-inverse-bg, #1e293b)",
  color: "var(--app-on-strong, #ffffff)",
  fontSize: "var(--text-sm, 12px)",
  fontWeight: 400,
  lineHeight: 1.45,
  whiteSpace: "normal",
  textAlign: "left",
  boxShadow: "0 6px 16px rgba(0, 0, 0, 0.2)",
  pointerEvents: "none",
};

const MARKER: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 15,
  height: 15,
  padding: 0,
  borderRadius: "50%",
  border: "1px solid currentColor",
  background: "transparent",
  color: "inherit",
  opacity: 0.65,
  fontSize: 10,
  fontWeight: 700,
  lineHeight: 1,
  cursor: "help",
};

export interface HintProps {
  children: ReactNode;
  /** Field name for screen reader announcement: e.g. "Taxa" -> "Ajuda sobre Taxa". */
  about?: string;
}

export function Hint({ children, about }: Readonly<HintProps>) {
  const id = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <span
      className="app-field-hint-wrap"
      style={{
        position: "relative",
        display: "inline-flex",
        verticalAlign: "middle",
        marginLeft: 6,
      }}
    >
      <button
        type="button"
        aria-label={about ? `Ajuda sobre ${about}` : "Ajuda"}
        aria-describedby={id}
        aria-expanded={open}
        style={MARKER}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((current) => !current)}
      >
        ?
      </button>

      <span id={id} role="tooltip" style={open ? BUBBLE : VISUALLY_HIDDEN}>
        {children}
      </span>
    </span>
  );
}
