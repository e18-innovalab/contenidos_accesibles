import React, { useState } from 'react';
import loginBanner from '../../assets/login-banner.png';
import baLogo from '../../assets/BA.png';
import { useSignIn } from '@clerk/clerk-react';
import { ArrowLeft } from 'lucide-react';

interface LoginViewProps {
  onBackToLanding?: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onBackToLanding }) => {
  const [email, setEmail] = useState('');
  const { signIn, isLoaded } = useSignIn();

  const handleGoogleLogin = () => {
    if (!isLoaded) return;
    signIn.authenticateWithRedirect({
      strategy: 'oauth_google',
      redirectUrl: '/sso-callback',
      redirectUrlComplete: '/',
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleGoogleLogin();
  };

  return (
    <>
      <style>{`
        .login-page {
          display: flex;
          width: 100%;
          min-height: 100dvh;
          margin: 0;
          padding: 0;
          font-family: 'Open Sans', sans-serif;
          background-color: #ffffff;
        }

        .login-banner {
          display: none;
        }

        .login-panel {
          flex: 1;
          width: 100%;
          background-color: #ffffff;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 24px 20px 32px;
          box-sizing: border-box;
        }

        .login-header {
          display: flex;
          justify-content: flex-start;
          margin-bottom: 24px;
        }

        .login-card {
          max-width: 440px;
          width: 100%;
          margin: 0 auto;
          background-color: #f8f9fa;
          border: 1px solid #e9ecef;
          border-radius: 12px;
          padding: 28px 22px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
          box-sizing: border-box;
        }

        @media (min-width: 992px) {
          .login-page {
            height: 100vh;
            overflow: hidden;
          }

          .login-banner {
            display: block;
            flex: 1;
            background-image: url(${loginBanner});
            background-size: cover;
            background-position: center;
            background-color: #e5edef;
          }

          .login-panel {
            padding: 40px 60px;
            overflow-y: auto;
          }

          .login-header {
            margin-bottom: 0;
          }

          .login-card {
            padding: 40px;
          }
        }
      `}</style>

      <div className="login-page">
        {/* Columna Izquierda: solo visible en escritorio (>= 992px) */}
        <div className="login-banner" aria-hidden="true" />

        {/* Columna Derecha / Vista principal en celular */}
        <div className="login-panel">
          <div className="login-header">
            {onBackToLanding && (
              <button
                type="button"
                onClick={onBackToLanding}
                className="login-back-button"
              >
                <ArrowLeft size={16} />
                Volver a VIA
              </button>
            )}
            <img
              src={baLogo}
              alt="Buenos Aires Ciudad"
              style={{ height: '40px', width: 'auto', objectFit: 'contain' }}
            />
          </div>

          <div className="login-card">
            {/* Icono de Accesibilidad */}
            <div style={{ textAlign: 'center', marginBottom: '16px', color: '#6f42c1' }}>
              <i className="fas fa-hands-helping" style={{ fontSize: '2.2rem' }} />
            </div>

            {/* Títulos */}
            <h1
              style={{
                fontSize: '1.35rem',
                fontWeight: 'bold',
                textAlign: 'center',
                color: '#111827',
                margin: '0 0 6px 0',
              }}
            >
              Te damos la bienvenida a VIA
            </h1>
            <p
              style={{
                fontSize: '0.8rem',
                color: '#6b7280',
                textAlign: 'center',
                margin: '0 0 24px 0',
              }}
            >
              Visualización, Inclusión y Accesibilidad
            </p>

            {/* Formulario */}
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: '16px', textAlign: 'left' }}>
                <label
                  htmlFor="email"
                  style={{
                    display: 'block',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: '6px',
                  }}
                >
                  Iniciá sesión con
                </label>
                <input
                  type="email"
                  id="email"
                  placeholder="Introduce tu email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '0.9rem',
                    border: '1px solid #cbd5e1',
                    borderRadius: '6px',
                    outline: 'none',
                    backgroundColor: '#fff',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={!email}
                style={{
                  width: '100%',
                  padding: '10px',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  backgroundColor: email ? '#142850' : '#e2e6ea',
                  color: email ? '#ffffff' : '#6c757d',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: email ? 'pointer' : 'default',
                  transition: 'background 0.2s',
                }}
              >
                Continuar
              </button>
            </form>

            {/* Divisor con texto */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                textAlign: 'center',
                margin: '20px 0',
                color: '#9ca3af',
                fontSize: '0.75rem',
              }}
            >
              <div style={{ flex: 1, borderBottom: '1px solid #d1d5db' }} />
              <span style={{ padding: '0 10px', textTransform: 'lowercase' }}>
                o continuar con email
              </span>
              <div style={{ flex: 1, borderBottom: '1px solid #d1d5db' }} />
            </div>

            {/* Botón Google (Conectado a Clerk) */}
            <button
              type="button"
              onClick={handleGoogleLogin}
              style={{
                width: '100%',
                padding: '10px',
                fontSize: '0.9rem',
                fontWeight: 600,
                backgroundColor: '#ffde59',
                color: '#1f2937',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
            >
              <i
                className="fab fa-google"
                style={{ marginRight: '8px', color: '#dc2626' }}
              />
              Continúa con Google
            </button>

            {/* Registro */}
            <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.85rem' }}>
              <span style={{ color: '#6b7280' }}>¿Todavía no tenés cuenta?</span>
              <a
                href="#registro"
                style={{
                  color: '#7c3aed',
                  fontWeight: 'bold',
                  marginLeft: '4px',
                  textDecoration: 'none',
                }}
              >
                Registrate
              </a>
            </div>
          </div>

          <div />
        </div>
      </div>
    </>
  );
};

export default LoginView;