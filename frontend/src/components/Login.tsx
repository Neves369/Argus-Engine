import { useState } from 'react';
import loginBg from '../assets/backgrounds/login.jpeg';
import './Login.css';

interface LoginProps {
  onLogin?: () => void;
}

function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onLogin?.();
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
        <button className="login-submit" type="submit">
          Entrar
        </button>
      </form>
    </div>
  );
}

export default Login;
