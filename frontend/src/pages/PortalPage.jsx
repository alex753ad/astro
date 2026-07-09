/**
 * PortalPage.jsx — публичный read-only портал клиента (/portal/:token)
 * Карта клиента + домашние задания + PDF-отчёт, под брендом астролога.
 */

import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import NatalChart from '../components/NatalChart';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';
const BACKEND  = 'https://astro-production-abcc.up.railway.app';

export default function PortalPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/portal/${token}`)
      .then(r => { if (!r.ok) throw new Error('Портал недоступен'); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message));
  }, [token]);

  const downloadReport = () => {
    const a = document.createElement('a');
    a.href = `${BACKEND}/portal-report/${token}`;
    a.click();
  };

  if (error) return (
    <div style={s.page}><div style={s.center}><p style={{ color: '#f0a0a0' }}>{error}</p></div></div>
  );
  if (!data) return (
    <div style={s.page}><div style={s.center}><div style={s.logo}>☽ ✦ ☾</div><p style={{ color: '#9080b0' }}>Загрузка…</p></div></div>
  );

  const c = data.chart;

  return (
    <div style={s.page}>
      <header style={s.header}>
        <div style={s.logo}>☽ ✦ ☾</div>
        <span style={s.brand}>{data.astrologer_name}</span>
      </header>

      <main style={s.main}>
        <div style={s.titleBlock}>
          <h1 style={s.title}>Личный кабинет · {data.client_name}</h1>
          {c && <p style={s.subtitle}>{c.birth_date} · {c.birth_place}</p>}
        </div>

        {c && (
          <section style={s.card}>
            <div style={s.sectionTitle}>Натальная карта</div>
            <div style={s.chartWrap}>
              <NatalChart
                planets={c.planets}
                houses={c.houses}
                aspects={c.aspects}
                ascendant={c.ascendant}
                midheaven={c.midheaven}
                timeUnknown={c.time_unknown}
                transitPlanets={[]}
              />
            </div>
            {data.has_report && (
              <button style={s.btnPrimary} onClick={downloadReport}>📄 Скачать PDF-отчёт</button>
            )}
          </section>
        )}

        <section style={s.card}>
          <div style={s.sectionTitle}>Домашние задания</div>
          {data.assignments.length === 0 ? (
            <p style={s.subtitle}>Пока заданий нет.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {data.assignments.map((a, i) => (
                <div key={i} style={s.assignment}>
                  <div style={s.assignmentHead}>
                    {a.date}{a.topic ? ` · ${a.topic}` : ''}
                  </div>
                  <div style={s.assignmentBody}>{a.assignment}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        <p style={s.promo}>
          работает на <strong>Astrea</strong> · astreatime.ru
        </p>
      </main>
    </div>
  );
}

const s = {
  page: { minHeight: '100vh', background: 'linear-gradient(160deg, #0e0c1a 0%, #1a1030 100%)', color: '#fff', fontFamily: "'Segoe UI', Arial, sans-serif" },
  center: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 16 },
  logo: { fontSize: 22, color: '#c9a8ff' },
  header: { display: 'flex', alignItems: 'center', gap: 12, padding: '20px 32px', borderBottom: '1px solid rgba(112,80,200,0.2)' },
  brand: { fontSize: 18, fontWeight: 700, color: '#c9a8ff', letterSpacing: 0.5 },
  main: { maxWidth: 720, margin: '0 auto', padding: '32px 20px 60px', display: 'flex', flexDirection: 'column', gap: 20 },
  titleBlock: {},
  title: { margin: '0 0 6px', fontSize: 26, fontWeight: 700, color: '#f0e8ff' },
  subtitle: { margin: 0, fontSize: 14, color: '#9080b0' },
  card: { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(112,80,200,0.2)', borderRadius: 20, padding: '24px' },
  sectionTitle: { fontSize: 13, fontWeight: 700, color: '#9060C8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 16 },
  chartWrap: { display: 'flex', justifyContent: 'center', marginBottom: 16 },
  assignment: { borderLeft: '3px solid #9060C8', paddingLeft: 14 },
  assignmentHead: { fontSize: 12, color: '#9080b0', marginBottom: 4 },
  assignmentBody: { fontSize: 14, color: '#e0d0ff', lineHeight: 1.6, whiteSpace: 'pre-wrap' },
  btnPrimary: { background: 'linear-gradient(135deg, #9060C8, #C060A0)', color: '#fff', border: 'none', borderRadius: 12, padding: '12px 24px', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' },
  promo: { fontSize: 13, color: '#6050a0', textAlign: 'center', marginTop: 8 },
};
