/**
 * GuestCreateScreen.jsx — построить карту без регистрации (решение владельца
 * 27.09.2026: до регистрации человек видит свою карту и прогноз).
 *
 * Та же форма, что на вкладке «Карта», с галочкой согласия (у гостя данные
 * рождения идут до флажка на регистрации). Карта сервером сохраняется
 * анонимной на 7 дней; здесь запоминаются её id и токен (lib/guestChart.js),
 * и гость попадает в ленту.
 */

import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ChartCreateView from '../components/ChartCreateView';
import { setGuestChart } from '../lib/guestChart';

const GUEST_DAYS = 7;   // = срок access_token анонимной карты (main.py, calculate_chart)

export default function GuestCreateScreen() {
  const navigate = useNavigate();

  const onCreated = useCallback((id, chart) => {
    setGuestChart({
      id,
      token: chart?.access_token,
      name: chart?.name,
      // Срок считаем от ответа: сервер ставит ровно 7 суток от построения, а
      // сама карта после срока уже не откроется — здесь он нужен только,
      // чтобы не открыть ленту, которая ответит 404.
      expiresAt: new Date(Date.now() + GUEST_DAYS * 86400000).toISOString(),
    });
    navigate('/app/feed', { replace: true });
  }, [navigate]);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', paddingTop: 'env(safe-area-inset-top)' }}>
      <ChartCreateView guest onCancel={() => navigate('/login', { replace: true })} onCreated={onCreated} />
    </div>
  );
}
