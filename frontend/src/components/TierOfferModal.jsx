import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Link } from "react-router-dom";
import { TIER_NAMES, tierPriceLabel } from "../constants";
import { offerFor } from "../lib/offerRule";
import { ACCESS_TERM, catalogItem, tierCard } from "../lib/tierCatalog";
import { tierAccusative } from "../mobile/lib/ruDeclension";

/*
  TierOfferModal — одно окно предложения тарифа на вебе (решение владельца
  28.09.2026). Заменило три: PaywallModal, PlanComparisonModal и
  LyraPaywallModal — у каждого был свой набор пунктов, и окно при окончании
  чата не упоминало чат вовсе.

  Порядок сверху вниз одинаков с листом в приложении:
    1. заголовок — то, что человек пытался сделать (пункт каталога);
    2. что случилось (`state`, например «Пробные сообщения закончились»);
    3. пояснение пункта;
    4. карточки тарифов по lib/offerRule.js — этот пункт первой строкой и
       подсвечен, дальше «Всё из …, плюс:».
  Пункты — только из lib/tierCatalog.js. Своих текстов тарифа здесь нет.

  Орион на вебе не продаётся (на /pricing — «Скоро»), поэтому sellable —
  Вега и Лира, как в приложении.

  Построено по DESIGN_SYSTEM.md: только CSS-переменные, инлайн-стили; тень
  кнопки в whileHover — целым токеном (frontend/CLAUDE.md, Framer Motion).
*/

const DISPLAY = "var(--font-display)";
const BODY = "var(--font-body)";
const SELLABLE = ["lite", "pro"];

function Svg({ children, size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

function PlanCard({ tier, feature, recommended, onChoose, busy, reduce }) {
  // Кратко: подсвеченная строка + главные пункты (OFFER_MAIN в каталоге),
  // полный список — на /pricing по ссылке под ними.
  const card = tierCard(tier, { focus: feature, brief: true });
  const [first, ...rest] = card.lines;
  const hl = first?.hl ? first : null;
  const others = hl ? rest : card.lines;
  return (
    <div
      style={{
        flex: "1 1 200px",
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-deeper)",
        border: recommended ? "1.5px solid var(--accent)" : "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
        <span style={{ fontFamily: DISPLAY, fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
          {TIER_NAMES[tier]}
        </span>
        <span style={{ fontFamily: BODY, fontVariantNumeric: "tabular-nums", fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
          {tierPriceLabel(tier)}
          <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-secondary)" }}> / мес</span>
        </span>
      </div>

      {hl && (
        <div
          style={{
            background: "var(--accent-muted)",
            color: "var(--accent-fg)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 10px",
            fontSize: 13.5,
            fontWeight: 600,
            lineHeight: 1.4,
            marginBottom: 10,
          }}
        >
          {hl.text}
        </div>
      )}

      {card.from && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>{card.from}</div>
      )}
      <ul style={{ listStyle: "none", margin: "0 0 10px", padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        {others.map((l) => (
          <li key={l.key} style={{ display: "flex", gap: 8, fontSize: 13, lineHeight: 1.45, color: "var(--text-primary)" }}>
            <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}>
              <Svg size={15}><path d="M20 6 9 17l-5-5" /></Svg>
            </span>
            {l.text}
          </li>
        ))}
      </ul>
      <Link to="/pricing" style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-fg)", marginBottom: 16, flexGrow: 1 }}>
        Все возможности тарифа
      </Link>

      <motion.button
        type="button"
        onClick={() => onChoose(tier)}
        disabled={busy}
        whileHover={reduce || busy ? undefined : recommended
          ? { y: -2, background: "var(--accent-glow)", boxShadow: "var(--shadow-accent)" }
          : { y: -1, boxShadow: "var(--shadow-card)" }}
        whileTap={{ scale: 0.97 }}
        style={{
          height: 44,
          width: "100%",
          borderRadius: "var(--radius-lg)",
          fontFamily: DISPLAY,
          fontSize: 14,
          fontWeight: 700,
          cursor: busy ? "default" : "pointer",
          opacity: busy ? 0.6 : 1,
          ...(recommended
            ? { background: "var(--accent)", color: "#ffffff", border: "none" }
            : { background: "var(--bg-card)", color: "var(--text-primary)", border: "1.5px solid var(--border)" }),
        }}
      >
        {busy ? "Открываем оплату…" : `Оформить ${tierAccusative(TIER_NAMES[tier])}`}
      </motion.button>
    </div>
  );
}

/**
 * @param {{
 *   open: boolean, onClose: () => void,
 *   feature: string — ключ offerRule.js (chat, chat_limit, transit, transit_limit,
 *     planner_period, planner_moon, planner_longterm, interpretation),
 *   tier: string — текущий тариф,
 *   state?: string — что случилось,
 *   contextLabel?: string — над заголовком (например, сам транзит),
 *   onChoose: (tier: string) => void, busy?: boolean,
 * }} props
 */
export default function TierOfferModal({ open, onClose, feature, tier, state, contextLabel, onChoose, busy = false }) {
  const reduce = useReducedMotion();
  const item = catalogItem(feature);
  const offer = offerFor(feature, tier || "free", { sellable: SELLABLE });
  const tiers = offer ? [offer.primary, offer.alt].filter(Boolean) : [];

  return (
    <AnimatePresence>
      {open && item && (
        <motion.div
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 16, background: "rgba(15,10,26,0.7)", backdropFilter: "blur(4px)",
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={item.title}
            onClick={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            style={{
              position: "relative",
              width: "100%",
              maxWidth: tiers.length > 1 ? 560 : 420,
              maxHeight: "calc(100vh - 32px)",
              overflowY: "auto",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-xl)",
              padding: "26px 24px 20px",
              boxShadow: "var(--shadow-overlay)",
              fontFamily: BODY,
              color: "var(--text-primary)",
            }}
          >
            <button
              type="button"
              aria-label="Закрыть"
              onClick={onClose}
              style={{
                position: "absolute", top: 14, right: 14, width: 28, height: 28, padding: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                border: "none", background: "transparent", color: "var(--text-secondary)", cursor: "pointer",
              }}
            >
              <Svg size={18}><path d="M18 6 6 18M6 6l12 12" /></Svg>
            </button>

            {contextLabel && (
              <p style={{ margin: "0 0 4px", paddingRight: 28, fontSize: 12, fontWeight: 600, color: "var(--accent-fg)" }}>
                {contextLabel}
              </p>
            )}
            <h2 style={{ margin: "0 0 6px", paddingRight: 28, fontFamily: DISPLAY, fontSize: 20, fontWeight: 600, lineHeight: 1.3 }}>
              {item.title}
            </h2>
            {state && (
              <p style={{ margin: "0 0 6px", fontSize: 15, lineHeight: 1.5, color: "var(--text-primary)" }}>
                {/* quotaEndedText отдаётся без точки — её дописывает тот, кто продолжает фразу; здесь строка стоит одна. */}
                {/[.!?…]$/.test(state) ? state : `${state}.`}
              </p>
            )}
            {item.about && (
              <p style={{ margin: "0 0 18px", fontSize: 14, lineHeight: 1.55, color: "var(--text-secondary)" }}>{item.about}</p>
            )}

            {tiers.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
                {tiers.map((t, i) => (
                  <PlanCard
                    key={t}
                    tier={t}
                    feature={feature}
                    recommended={i === tiers.length - 1}
                    onChoose={onChoose}
                    busy={busy}
                    reduce={reduce}
                  />
                ))}
              </div>
            ) : (
              <p style={{ margin: "0 0 14px", fontSize: 14, color: "var(--text-secondary)" }}>
                У тебя уже старший из доступных тарифов.
              </p>
            )}

            <div style={{ textAlign: "center" }}>
              <button
                type="button"
                onClick={onClose}
                style={{ border: "none", background: "transparent", color: "var(--text-secondary)", fontSize: 13, cursor: "pointer", padding: "4px 8px" }}
              >
                Не сейчас
              </button>
              <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--text-secondary)" }}>
                {ACCESS_TERM}
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
