import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

/*
  LyraPaywallModal — единое окно апселла тарифа «Лира».
  Построено по DESIGN_SYSTEM.md (v1.2): только CSS-переменные, инлайн-стили
  (без Tailwind-классов — §10), шрифты Space Grotesk / Inter, токены Modal/Button/Badge.

  Используется в двух местах:
    • Планер, кнопка «Открыть доступ»
    • Транзиты, кнопка «Интерпретация» (вместо старого маленького поповера)

  Пример:
    <LyraPaywallModal
      open={showPaywall}
      onClose={() => setShowPaywall(false)}
      onSubscribe={handleSubscribe}
      onEnterPromo={handlePromo}
      onContinueFree={() => setShowPaywall(false)}
      contextLabel={aspectName}   // напр. "Юпитер Трин Сатурн" (необязательно)
    />
*/

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

const DEFAULT_FEATURES = [
  { icon: "chat", text: "Чат с AI-астрологом Астрея, который уже знает вашу карту" },
  { icon: "telescope", text: "Разбор каждого транзита — что он значит и как его прожить" },
  { icon: "doc", text: "Глубокий разбор — от 1500 слов, 15 карт в месяц" },
  { icon: "calendar", text: "Планер Timeline на месяц вперёд и PDF-экспорт" },
  { icon: "users", text: "До 20 карт в месяц — для семьи и близких" },
];

function Icon({ name, size = 20 }) {
  const p = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  switch (name) {
    case "x":
      return (
        <svg {...p}>
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      );
    case "sparkles":
      return (
        <svg {...p}>
          <path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z" />
          <path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2z" />
        </svg>
      );
    case "chat":
      return (
        <svg {...p}>
          <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 8.9 8.9 0 0 1-4-1L3 21l2-5.5a8.4 8.4 0 0 1-1-4A8.4 8.4 0 0 1 12.5 3 8.4 8.4 0 0 1 21 11.5z" />
        </svg>
      );
    case "telescope":
      return (
        <svg {...p}>
          <path d="M4 15l6-2M14.5 4.5l4.8 2.6a2 2 0 0 1 .8 2.7l-1 1.8-8.3-4.5 1-1.8a2 2 0 0 1 2.7-.8z" />
          <path d="M9.6 8.9 3.8 11a2 2 0 0 0-1.1 2.6l.6 1.4a2 2 0 0 0 2.6 1L11 15" />
          <path d="M11 13.5 13 21M14 20l-3-6.5" />
        </svg>
      );
    case "doc":
      return (
        <svg {...p}>
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" />
          <path d="M14 3v5h5M9 13h6M9 17h6" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...p}>
          <rect x="3" y="4" width="18" height="17" rx="2" />
          <path d="M16 2v4M8 2v4M3 10h18" />
        </svg>
      );
    case "users":
      return (
        <svg {...p}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1A4 4 0 0 1 16 11" />
        </svg>
      );
    default:
      return null;
  }
}

export default function LyraPaywallModal({
  open,
  onClose,
  onSubscribe,
  onEnterPromo,
  onContinueFree,
  contextLabel,
  title = "Разбор этого транзита по вашей карте",
  subtitle = "AI-астролог Астрея помнит вашу карту и прошлые разговоры и объясняет, что каждый период значит именно для вас.",
  features = DEFAULT_FEATURES,
  price = "1 990 ₽",
}) {
  const reduce = useReducedMotion();

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
            background: "rgba(15,10,26,0.7)",
            backdropFilter: "blur(4px)",
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Тариф Лира"
            onClick={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            style={{
              position: "relative",
              width: "100%",
              maxWidth: 400,
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: 20,
              padding: "28px 28px 22px",
              boxShadow: "0 24px 60px rgba(0,0,0,0.40)",
              fontFamily: BODY,
              color: "var(--text-primary)",
            }}
          >
            <motion.button
              type="button"
              aria-label="Закрыть"
              onClick={onClose}
              whileHover={{ color: "var(--text-primary)" }}
              whileTap={{ scale: 0.92 }}
              style={{
                position: "absolute",
                top: 16,
                right: 16,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                padding: 0,
                border: "none",
                background: "transparent",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              <Icon name="x" size={18} />
            </motion.button>

            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: "var(--accent-muted)",
                color: "var(--accent-glow)",
                borderRadius: 8,
                padding: "4px 10px",
                fontFamily: DISPLAY,
                fontSize: 12,
                fontWeight: 600,
                marginBottom: 14,
              }}
            >
              <Icon name="sparkles" size={14} />
              Тариф Лира
            </div>

            {contextLabel && (
              <p
                style={{
                  margin: "0 0 4px",
                  fontFamily: DISPLAY,
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                  color: "var(--accent-glow)",
                }}
              >
                {contextLabel}
              </p>
            )}

            <h2
              style={{
                margin: "0 0 8px",
                fontFamily: DISPLAY,
                fontSize: 18,
                fontWeight: 600,
                lineHeight: 1.35,
                color: "var(--text-primary)",
              }}
            >
              {title}
            </h2>
            <p
              style={{
                margin: "0 0 20px",
                fontSize: 15,
                lineHeight: 1.6,
                color: "var(--text-secondary)",
              }}
            >
              {subtitle}
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
              {features.map((f, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}>
                    <Icon name={f.icon} size={20} />
                  </span>
                  <span style={{ fontSize: 15, lineHeight: 1.5, color: "var(--text-primary)" }}>
                    {f.text}
                  </span>
                </div>
              ))}
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 10,
                padding: "12px 0",
                borderTop: "1px solid var(--border)",
              }}
            >
              <span style={{ fontFamily: DISPLAY, fontSize: 22, fontWeight: 700 }}>{price}</span>
              <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>в месяц</span>
            </div>

            <motion.button
              type="button"
              onClick={onSubscribe}
              whileHover={
                reduce
                  ? undefined
                  : { y: -3, background: "var(--accent-glow)", boxShadow: "0 8px 24px rgba(139,92,246,0.32)" }
              }
              whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 90 }}
              style={{
                width: "100%",
                height: 44,
                margin: "6px 0 12px",
                border: "none",
                borderRadius: 16,
                background: "var(--accent)",
                color: "#ffffff",
                fontFamily: DISPLAY,
                fontSize: 15,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Перейти на тариф Лира
            </motion.button>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 14,
                marginBottom: 10,
              }}
            >
              <motion.button
                type="button"
                onClick={onEnterPromo}
                whileHover={{ color: "var(--accent-glow)" }}
                whileTap={{ scale: 0.98 }}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "var(--text-secondary)",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Ввести промокод
              </motion.button>
              <span style={{ color: "var(--border)" }}>·</span>
              <motion.button
                type="button"
                onClick={onContinueFree}
                whileHover={{ color: "var(--accent-glow)" }}
                whileTap={{ scale: 0.98 }}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "var(--text-secondary)",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Продолжить бесплатно
              </motion.button>
            </div>

            <p style={{ margin: 0, textAlign: "center", fontSize: 13, color: "var(--text-secondary)" }}>
              Отмена в любой момент · без обязательств
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
