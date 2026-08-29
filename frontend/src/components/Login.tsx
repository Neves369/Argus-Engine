import { useState } from 'react';
import loginBg from '../assets/backgrounds/login.jpeg';
import { login } from '../api/client';
import './Login.css';

interface LoginProps {
  onLogin?: () => void;
}

function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(password);
      if (result.authenticated) {
        onLogin?.();
      } else {
        setError('Falha na autenticação.');
      }
    } catch {
      setError('Senha inválida ou serviço indisponível.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="login-screen"
      style={{ backgroundImage: `url(${loginBg})` }}
    >
      <form className="login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">Argus Engine</h1>
        <div className="login-field">
          <label className="login-label" htmlFor="username">Usuário</label>
          <input
            id="username"
            className="login-input"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="login-field">
          <label className="login-label" htmlFor="password">Senha</label>
          <input
            id="password"
            className="login-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        {error && <div className="login-error">{error}</div>}
        <button className="login-submit" type="submit" disabled={submitting}>
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}

export default Login;
