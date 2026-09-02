/**
 * Footer — общий футер на всех страницах (задача: сайт для модерации ЮKassa).
 * Ссылки + ФИО/статус/ИНН продавца — требование ЗоЗПП, видно на каждой странице.
 */

import { Link } from 'react-router-dom';

const LINKS = [
  { to: '/pricing', label: 'Тарифы' },
  { to: '/terms', label: 'Оферта' },
  { to: '/privacy', label: 'Политика обработки персональных данных' },
  { to: '/requisites', label: 'Реквизиты' },
  { to: '/requisites', label: 'Контакты' },
];

export default function Footer() {
  return (
    <footer className="border-t border-brand-border py-5 text-center text-brand-muted text-xs bg-brand-card/50">
      <div>
        Aristea Timeline © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris
      </div>
      <div style={{ marginTop: 6 }}>
        {LINKS.map((l, i) => (
          <span key={`${l.to}-${l.label}`}>
            {i > 0 && <span className="mx-2">·</span>}
            <Link to={l.to} className="hover:text-slate-600 transition-colors">{l.label}</Link>
          </span>
        ))}
      </div>
      <div style={{ marginTop: 6 }}>
        Оносова Наталья Юрьевна · Самозанятая (плательщик НПД) · ИНН 615011483048
      </div>
    </footer>
  );
}
