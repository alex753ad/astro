import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import BirthForm from '../components/BirthForm';
import { calculateChart } from '../api/client';

// Tooltip-подсказки для астро-терминов
const TOOLTIPS = {
  ASC: 'Асцендент (ASC) — точка горизонта на востоке в момент рождения. Показывает, как вы воспринимаетесь окружающими.',
  MC:  'Середина Неба (MC) — высшая точка неба в момент рождения. Связана с карьерой и жизненным призванием.',
  'аспекты': 'Аспекты — угловые соотношения между планетами. Трин и секстиль — гармоничные, квадрат и оппозиция — напряжённые.',
  'дома': 'Дома — 12 секторов карты, каждый отвечает за свою сферу жизни: 1-й — личность, 7-й — партнёрство, 10-й — карьера.',
};

function TooltipBadge({ term }) {
  const [visible, setVisible] = useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <span
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 16, height: 16, borderRadius: 8,
          background: 'rgba(124,108,255,0.2)', color: '#7C6CFF',
          fontSize: 10, fontWeight: 700, cursor: 'help',
          border: '1px solid rgba(124,108,255,0.4)',
          userSelect: 'none',
        }}
      >?</span>
      {visible && (
        <div style={{
          position: 'absolute', bottom: '100%', left: '50%',
          transform: 'translateX(-50%)',
          marginBottom: 6, zIndex: 100,
          background: '#1a1a2e', border: '1px solid rgba(124,108,255,0.3)',
          borderRadius: 10, padding: '10px 14px',
          width: 220, fontSize: 12, lineHeight: 1.6,
          color: '#C8CAD8', boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          pointerEvents: 'none',
        }}>
          <strong style={{ color: '#7C6CFF' }}>{term}</strong><br />
          {TOOLTIPS[term]}
        </div>
      )}
    </span>
  );
}

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
        sessionStorage.setItem('pending_chart_id', chart.id);
      }
      navigate(`/chart/${chart.id}`);
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

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      {/* Hero */}
      <div className="text-center mb-12">
        <h1 className="font-display text-4xl md:text-5xl font-bold mb-4">
          <span className="text-brand-glow">Натальная карта</span>
          <br />
          <span className="text-brand-text/80 text-2xl md:text-3xl">
            с AI-интерпретацией
          </span>
        </h1>
        <p className="text-brand-muted max-w-md mx-auto leading-relaxed">
          Точные астрономические расчёты Swiss Ephemeris + персонализированная интерпретация
          от GPT-4o. Укажите данные рождения и получите полный анализ за секунды.
        </p>
        {!currentUser && (
          <p style={{ fontSize: 13, color: '#7C6CFF', marginTop: 10 }}>
            Регистрация не нужна — просто введите данные рождения ↓
          </p>
        )}
      </div>

      {/* Form */}
      <BirthForm onSubmit={handleSubmit} loading={loading} />

      {/* Error */}
      {error && (
        <div className="max-w-lg mx-auto mt-4 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm whitespace-pre-line">
          {error}
        </div>
      )}

      {/* Features */}
      <div className="grid md:grid-cols-3 gap-6 mt-16 text-center">
        {[
          {
            icon: '⚙️',
            title: 'Swiss Ephemeris',
            desc: 'Погрешность < 1 угловой секунды. Золотой стандарт расчётов.',
          },
          {
            icon: '✦',
            title: 'AI-интерпретация',
            desc: 'Персонализированный нарратив от GPT-4o. Не шаблоны.',
          },
          {
            icon: '🔒',
            title: 'Приватность',
            desc: 'Данные хранятся в зашифрованной базе. Удаление в один клик.',
          },
        ].map((f) => (
          <div key={f.title} className="glass-card p-6">
            <div className="text-2xl mb-3">{f.icon}</div>
            <h3 className="font-display font-bold mb-2">{f.title}</h3>
            <p className="text-sm text-brand-muted">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Астро-глоссарий с подсказками */}
      <div style={{
        marginTop: 40, padding: '20px 24px', borderRadius: 16,
        background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
      }}>
        <p style={{ fontSize: 12, color: '#8B8FA3', marginBottom: 12, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Что означают термины в карте
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {Object.keys(TOOLTIPS).map(term => (
            <span key={term} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#C8CAD8' }}>
              {term} <TooltipBadge term={term} />
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
