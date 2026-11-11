import React, { useState } from 'react';
import loginBanner from '../../assets/login-banner.png';
import baLogo from '../../assets/BA.png';

interface LoginViewProps {
  onLoginSuccess: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLoginSuccess();
  };

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', margin: 0, padding: 0, overflow: 'hidden', fontFamily: "'Open Sans', sans-serif" }}>
      
      {/* Columna Izquierda: Imagen del globo terráqueo y libros */}
      <div 
        style={{
          flex: '1',
          backgroundImage: `url(${loginBanner})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundColor: '#e5edef'
        }}
        className="d-none d-lg-block"
      />

      {/* Columna Derecha: Contenedor principal de acceso */}
      <div style={{ 
        flex: '1', 
        backgroundColor: '#ffffff', 
        display: 'flex', 
        flexDirection: 'column', 
        justifyContent: 'space-between', 
        padding: '40px 60px',
        overflowY: 'auto'
      }}>
        
        {/* Logo institucional de Buenos Aires Ciudad */}
        <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
          <img 
            src={baLogo} 
            alt="Buenos Aires Ciudad" 
            style={{ height: '42px', width: 'auto', objectFit: 'contain' }} 
          />
        </div>

        {/* Tarjeta central */}
        <div style={{ 
          maxWidth: '440px', 
          width: '100%', 
          margin: '0 auto', 
          backgroundColor: '#f8f9fa', 
          border: '1px solid #e9ecef', 
          borderRadius: '12px', 
          padding: '40px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.03)'
        }}>
          
          {/* Icono de Accesibilidad */}
          <div style={{ textAlign: 'center', marginBottom: '16px', color: '#6f42c1' }}>
            <i className="fas fa-hands-helping" style={{ fontSize: '2.5rem' }}></i>
          </div>

          {/* Títulos */}
          <h1 style={{ fontSize: '1.4rem', fontWeight: 'bold', textAlign: 'center', color: '#111827', margin: '0 0 6px 0' }}>
            Te damos la bienvenida a VIA
          </h1>
          <p style={{ fontSize: '0.8rem', color: '#6b7280', textAlign: 'center', margin: '0 0 24px 0' }}>
            Visualización, Inclusión y Accesibilidad
          </p>

          {/* Formulario */}
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '16px', textAlign: 'left' }}>
              <label htmlFor="email" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
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
                  backgroundColor: '#fff'
                }}
                required
              />
            </div>

            <button 
              type="submit" 
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
                transition: 'background 0.2s'
              }}
              disabled={!email}
            >
              Continuar
            </button>
          </form>

          {/* Divisor con texto */}
          <div style={{ display: 'flex', alignItems: 'center', textAlign: 'center', margin: '20px 0', color: '#9ca3af', fontSize: '0.75rem' }}>
            <div style={{ flex: 1, borderBottom: '1px solid #d1d5db' }}></div>
            <span style={{ padding: '0 10px', textTransform: 'lowercase' }}>o continuar con email</span>
            <div style={{ flex: 1, borderBottom: '1px solid #d1d5db' }}></div>
          </div>

          {/* Botón Google */}
          <button 
            type="button" 
            onClick={onLoginSuccess}
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
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
            }}
          >
            <i className="fab fa-google" style={{ marginRight: '8px', color: '#dc2626' }}></i> Continúa con Google
          </button>

          {/* Registro */}
          <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.85rem' }}>
            <span style={{ color: '#6b7280' }}>¿Todavía no tenés cuenta?</span> 
            <a href="#registro" style={{ color: '#7c3aed', fontWeight: 'bold', marginLeft: '4px', textDecoration: 'none' }}>Registrate</a>
          </div>

        </div>

        <div></div> {/* Espaciador inferior */}

      </div>
    </div>
  );
};

export default LoginView;