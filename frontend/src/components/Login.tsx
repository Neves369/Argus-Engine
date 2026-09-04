import { useEffect, useState } from 'react';
import loginBg from '../assets/backgrounds/login.jpeg';
import { ApiError, getMe, login } from '../api/client';
import './Login.css';

interface LoginProps {
  onLogin?: () => void;
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Senha inválida.';
    if (err.status === 409) return 'Login desativado: o backend está em modo aberto (sem UI_PASSWORD).';
  }
  return 'Serviço indisponível.';
}

function Login({ onLogin }: LoginProps) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState(true);
  const [entered, setEntered] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    let cancelled = false;
    setChecking(true);
    getMe()
      .then((me) => {
        if (cancelled) return;
        if (!me.ui_enabled) {
          onLogin?.();
          setEntered(true);
        }
      })
      .catch(() => {
        // Não foi possível determinar o modo: mostra o formulário e deixa o
        // submit reportar o erro real (ex.: serviço indisponível).
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onLogin]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(password);
      if (result.authenticated) {
        onLogin?.();
        setEntered(true);
      } else {
        setError('Falha na autenticação.');
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (checking || entered) {
    return <div className="login-screen" style={{ backgroundImage: `url(${loginBg})` }} />;
  }

  return (
    <div
      className="login-screen"
      style={{ backgroundImage: `url(${loginBg})` }}
    >
      <form className="login-card" onSubmit={handleSubmit}>
        <h1 className="login-title">Argus Engine</h1>
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
