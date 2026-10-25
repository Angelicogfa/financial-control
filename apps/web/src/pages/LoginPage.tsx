import { useState, type FormEvent } from "react";

import { login } from "../api/auth";
import { errorMessage } from "../api/http";

export function LoginPage({
  notice,
  onLoggedIn,
}: Readonly<{ notice?: string; onLoggedIn: (username: string) => void }>) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      onLoggedIn(await login(username.trim(), password));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-canvas">
      <form className="app-card app-card-padded login-card" onSubmit={submit} aria-label="Entrar">
        <div className="app-brand" style={{ padding: 0 }}>
          <span className="app-brand-mark" aria-hidden="true">
            FC
          </span>
          <div className="app-brand-text">
            <span className="app-brand-title">Financial Control</span>
            <span className="app-brand-subtitle">Entre para acessar sua carteira</span>
          </div>
        </div>
        {notice && (
          <div className="app-info-banner" role="status">
            {notice}
          </div>
        )}
        {error && (
          <div className="app-error-banner" role="alert">
            {error}
          </div>
        )}
        <div className="app-field">
          <label htmlFor="login-username">Usuário</label>
          <input
            id="login-username"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="app-field">
          <label htmlFor="login-password">Senha</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="app-primary-button" disabled={submitting}>
          {submitting ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
