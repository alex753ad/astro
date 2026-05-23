import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import BirthForm from '../components/BirthForm';
import { calculateChart } from '../api/client';

export default function HomePage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (data) => {
    setLoading(true);
    setError('');

    try {
      const chart = await calculateChart(data);
      navigate(`/chart/${chart.id}`);
    } catch (err) {
      // Handle ambiguous time error
      if (err.data?.type === 'ambiguous_time') {
        setError(
          `${err.data.message}\nВарианты: ${err.data.options?.join(' или ')}`
        );
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
          { icon: '⚙️', title: 'Swiss Ephemeris', desc: 'Погрешность < 1 угловой секунды. Золотой стандарт расчётов.' },
          { icon: '✦', title: 'AI-интерпретация', desc: 'Персонализированный нарратив от GPT-4o. Не шаблоны.' },
          { icon: '🔒', title: 'Приватность', desc: 'Данные хранятся в зашифрованной базе. Удаление в один клик.' },
        ].map((f) => (
          <div key={f.title} className="glass-card p-6">
            <div className="text-2xl mb-3">{f.icon}</div>
            <h3 className="font-display font-bold mb-2">{f.title}</h3>
            <p className="text-sm text-brand-muted">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
