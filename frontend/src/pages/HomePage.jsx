import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import BirthForm from '../components/BirthForm';
import { calculateChart } from '../api/client';

export default function HomePage({ currentUser, onShowAuth }) {
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (data) => {
    setLoading(true);
    setError('');
    try {
      const chart = await calculateChart(data);
      if (!currentUser) {
        localStorage.setItem('anonymous_chart', JSON.stringify({
          data: data,
          timestamp: Date.now(),
          expiresAt: Date.now() + 24 * 60 * 60 * 1000,
        }));
        sessionStorage.setItem('anonymous_chart_result', JSON.stringify(chart));
      }
      navigate(chart.id ? `/chart/${chart.id}` : '/chart/anonymous');
    } catch (err) {
      if (err.data?.type === 'ambiguous_time') {
        setError(`${err.data.message}\nВарианты: ${err.data.options?.join(' или ')}`);
      } else {
        setError(err.message || 'Ошибка расчёта. Попробуйте ещё раз.');
      }
    } finally {
      setLoading(false);
    }
  };

  const schemaOrg = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Astrea Timeline',
    url: 'https://astreatime.ru',
    applicationCategory: 'LifestyleApplication',
    operatingSystem: 'Web',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'RUB',
      description: 'Бесплатный тариф с базовыми функциями',
    },
    description: 'Натальные карты, AI-интерпретации транзитов и персональный астро-планер на основе Swiss Ephemeris и GPT-4o.',
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #f8f0ff 0%, #f0e8ff 20%, #fce8f4 45%, #e8f0ff 70%, #f0f8ff 100%)',
      fontFamily: '"Space Grotesk", system-ui, sans-serif',
      padding: '32px 24px 60px',
    }}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaOrg) }}
      />
      {/* Back link */}
      <div style={{ maxWidth: 500, margin: '0 auto 24px' }}>
        <Link
          to="/"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 14, color: '#8B5CF6', textDecoration: 'none',
            fontWeight: 600,
          }}
          onMouseEnter={e => e.currentTarget.style.opacity = '0.75'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          ← На главную
        </Link>
      </div>

      {/* Form */}
      <BirthForm onSubmit={handleSubmit} loading={loading} />

      {/* Error */}
      {error && (
        <div style={{
          maxWidth: 500, margin: '16px auto 0',
          padding: '14px 18px', borderRadius: 12,
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)',
          color: '#EF4444', fontSize: 13,
          whiteSpace: 'pre-line',
        }}>
          {error}
        </div>
      )}
    </div>
  );
}
