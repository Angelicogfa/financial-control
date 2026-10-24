/** Single-user login screen shown while there is no valid session (item 9.5). */

import React, { useState } from "react";
import { login } from "../services/authClient";

interface LoginPageProps {
  notice?: string;
  onLoggedIn: (username: string) => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ notice, onLoggedIn }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      onLoggedIn(await login(username.trim(), password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-canvas">
      <form className="panel-card login-card" onSubmit={handleSubmit} aria-label="Entrar">
        <div className="brand-group" style={{ marginBottom: "16px" }}>
          <div className="brand-logo">FC</div>
          <div>
            <h1 className="panel-title">Financial Control</h1>
            <p className="panel-subtitle">Entre para acessar sua carteira</p>
          </div>
        </div>

        {notice && (
          <div className="alert alert-info" role="status">
            {notice}
          </div>
        )}
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        <div className="form-field">
          <label htmlFor="login-username">Usuário</label>
          <input
            id="login-username"
            className="std-input"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="form-field">
          <label htmlFor="login-password">Senha</label>
          <input
            id="login-password"
            type="password"
            className="std-input"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
};
