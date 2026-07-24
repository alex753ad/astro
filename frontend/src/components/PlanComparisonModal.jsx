import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

/*
  PlanComparisonModal — окно для пользователей на Free.
  Показывает два тарифа рядом (Вега и Лира), Лира выделена как рекомендованная.
  Цель — увести на Лиру, но дать и более дешёвый вход (Вега).

  Для пользователей, уже находящихся на Веге, используйте LyraPaywallModal
  (одиночный апселл на Лиру).

  Построено по DESIGN_SYSTEM.md (v1.2): только CSS-переменные, инлайн-стили,
  шрифты Space Grotesk / Inter, токены Modal/Button/Card/Badge.

  Контент по умолчанию — общий. Для контекста вкладки можно передать свои
  vega.features / lyra.features (напр. в Транзитах — про AI-разбор).

  Пример:
    <PlanComparisonModal
      open={showPaywall}
      onClose={() => setShowPaywall(false)}
      onChooseVega={goVega}
      onChooseLyra={goLyra}
      onContinueFree={() => setShowPaywall(false)}
      contextLabel={aspectName}   // необязательно
    />
*/

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

const DEFAULT_VEGA = {
  name: "Вега",
  price: "790 ₽",
  features: ["Индивидуальные рекомендации на месяц", "Лунный календарь"],
};

const DEFAULT_LYRA = {
  name: "Лира",
  price: "1 990 ₽",
  recommended: true,
  features: [
    "Всё из Веги + Долгосрочные периоды",
    "Чат с Астреей — персональный разбор в любой момент",
    "PDF и до 5 карт для семьи",
  ],
};

function Svg({ children, size = 20 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

const IconX = () => (
  <Svg size={18}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);
const IconCheck = () => (
  <Svg size={16}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);
const IconSpark = () => (
  <Svg size={14}>
    <path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z" />
  </Svg>
);

function PlanCard({ plan, cta, onChoose, recommended, reduce }) {
  return (
    <div
      style={{
        flex: "1 1 190px",
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-deeper)",
        border: recommended ? "1.5px solid var(--accent)" : "1px solid var(--border)",
        borderRadius: 16,
        boxShadow: recommended ? "0 0 15px rgba(139,92,246,0.10)" : "none",
        padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, minHeight: 22 }}>
        <span style={{ fontFamily: DISPLAY, fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
          {plan.name}
        </span>
        {recommended && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              background: "var(--accent-muted)",
              color: "var(--accent-glow)",
              borderRadius: 8,
              padding: "2px 8px",
              fontFamily: DISPLAY,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            <IconSpark />
            Рекомендуем
          </span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 14 }}>
        <span style={{ fontFamily: DISPLAY, fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          {plan.price}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>/мес</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 16, flexGrow: 1 }}>
        {plan.features.map((f, i) => (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}>
              <IconCheck />
            </span>
            <span style={{ fontSize: 13, lineHeight: 1.45, color: "var(--text-primary)" }}>{f}</span>
          </div>
        ))}
      </div>

      <motion.button
        type="button"
        onClick={onChoose}
        whileHover={
          reduce
            ? undefined
            : recommended
            ? { y: -3, background: "var(--accent-glow)", boxShadow: "0 8px 24px rgba(139,92,246,0.32)" }
            : { y: -1, borderColor: "var(--accent-muted)", boxShadow: "0 4px 12px rgba(0,0,0,0.12)" }
        }
        whileTap={{ scale: recommended ? 0.95 : 0.97 }}
        transition={{ type: "spring", stiffness: 90 }}
        style={{
          height: 44,
          width: "100%",
          borderRadius: 16,
          fontFamily: DISPLAY,
          fontSize: 14,
          fontWeight: 700,
          cursor: "pointer",
          ...(recommended
            ? { background: "var(--accent)", color: "#ffffff", border: "none" }
            : {
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                border: "1.5px solid var(--border)",
              }),
        }}
      >
        {cta}
      </motion.button>
    </div>
  );
}

export default function PlanComparisonModal({
  open,
  onClose,
  onChooseVega,
  onChooseLyra,
  onContinueFree,
  contextLabel,
  title = "Откройте больше в Astrea Timeline",
  vega = DEFAULT_VEGA,
  lyra = DEFAULT_LYRA,
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
            aria-label="Выбор тарифа"
            onClick={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            style={{
              position: "relative",
              width: "100%",
              maxWidth: 480,
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: 20,
              padding: "26px 24px 20px",
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
              <IconX />
            </motion.button>

            {contextLabel && (
              <p
                style={{
                  margin: "0 0 4px",
                  fontFamily: DISPLAY,
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--accent-glow)",
                }}
              >
                {contextLabel}
              </p>
            )}

            <h2
              style={{
                margin: "0 0 18px",
                paddingRight: 28,
                fontFamily: DISPLAY,
                fontSize: 18,
                fontWeight: 600,
                lineHeight: 1.35,
                color: "var(--text-primary)",
              }}
            >
              {title}
            </h2>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
              <PlanCard
                plan={vega}
                cta="Выбрать Вегу"
                onChoose={onChooseVega}
                recommended={false}
                reduce={reduce}
              />
              <PlanCard
                plan={lyra}
                cta="Перейти на Лиру"
                onChoose={onChooseLyra}
                recommended
                reduce={reduce}
              />
            </div>

            <div style={{ textAlign: "center" }}>
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
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
