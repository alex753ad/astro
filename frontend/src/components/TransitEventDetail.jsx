/**
 * TransitEventDetail — Interpretation panel for a single transit event.
 * 
 * Production version: connects to real SSE endpoint
 * POST /api/v1/chart/{chartId}/transits/event/interpret
 *
 * Props:
 *   event      — transit event object from API
 *   chartId    — natal chart ID
 *   onClose    — callback to close panel
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { streamTransitEventInterpretation } from "../api/client";

const ASPECT_LABELS_RU = {
  conjunction: "Соединение",
  sextile: "Секстиль",
  square: "Квадрат",
  trine: "Трин",
  opposition: "Оппозиция",
};

const PLANET_GLYPHS = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
};

const ASPECT_COLORS = {
  conjunction: "#F59E0B",
  sextile: "#3B82F6",
  square: "#EF4444",
  trine: "#3B82F6",
  opposition: "#EF4444",
};

export default function TransitEventDetail({ event, chartId, onClose }) {
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const textRef = useRef(null);

  const loadInterpretation = useCallback(async () => {
    if (!event || !chartId) return;

    setText("");
    setError(null);
    setStreaming(true);

    await streamTransitEventInterpretation(
      chartId,
      {
        transit_planet: event.transit_planet,
        natal_planet: event.natal_planet,
        aspect_type: event.aspect_type,
        date: event.date,
        orb: event.orb,
      },
      // onChunk
      (chunk) => setText(prev => prev + chunk),
      // onDone
      () => setStreaming(false),
      // onError
      (err) => {
        setError(err);
        setStreaming(false);
      },
    );
  }, [event, chartId]);

  useEffect(() => {
    loadInterpretation();
  }, [loadInterpretation]);

  // Auto-scroll during streaming
  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight;
    }
  }, [text]);

  if (!event) return null;

  const color = ASPECT_COLORS[event.aspect_type] || "#888";

  return (
    <div style={{
      background: "var(--card-bg, #141620)",
      borderRadius: 14,
      border: "1px solid var(--border, #1E2235)",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px",
        borderBottom: "1px solid var(--border, #1E2235)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 22 }}>{PLANET_GLYPHS[event.transit_planet] || "?"}</span>
            <span style={{ fontSize: 20, color, fontWeight: 700 }}>
              {event.aspect_type === "conjunction" ? "☌" :
               event.aspect_type === "sextile" ? "⚹" :
               event.aspect_type === "square" ? "□" :
               event.aspect_type === "trine" ? "△" : "☍"}
            </span>
            <span style={{ fontSize: 22 }}>{PLANET_GLYPHS[event.natal_planet] || "?"}</span>
          </div>
          <div style={{
            fontSize: 15,
            fontWeight: 600,
            color: "var(--text-primary, #E8EAF0)",
          }}>
            {event.transit_planet} {ASPECT_LABELS_RU[event.aspect_type]?.toLowerCase()} {event.natal_planet}
          </div>
          <div style={{
            fontSize: 12,
            color: "var(--text-secondary, #8B8FA3)",
            marginTop: 4,
          }}>
            {event.date} • Орб {event.orb?.toFixed(1)}°
            {event.exact_date && ` • Точно: ${event.exact_date}`}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            background: "none",
            border: "none",
            color: "var(--text-secondary, #8B8FA3)",
            fontSize: 22,
            cursor: "pointer",
            padding: "4px 8px",
            borderRadius: 8,
          }}
        >
          ✕
        </button>
      </div>

      {/* Interpretation body */}
      <div
        ref={textRef}
        style={{
          padding: 20,
          fontSize: 14.5,
          lineHeight: 1.75,
          color: "var(--text-primary, #E8EAF0)",
          maxHeight: 400,
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          minHeight: 120,
        }}
      >
        {error ? (
          <div style={{
            textAlign: "center",
            padding: "20px 0",
            color: "var(--text-secondary, #8B8FA3)",
          }}>
            <div style={{ fontSize: 14, marginBottom: 12 }}>
              Не удалось загрузить интерпретацию
            </div>
            <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 16 }}>{error}</div>
            <button
              onClick={loadInterpretation}
              style={{
                padding: "8px 20px",
                borderRadius: 8,
                border: `1.5px solid ${color}`,
                background: "transparent",
                color,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Попробовать снова
            </button>
          </div>
        ) : text ? (
          <>
            {text}
            {streaming && (
              <span style={{
                display: "inline-block",
                width: 7,
                height: 18,
                background: color,
                marginLeft: 2,
                borderRadius: 2,
                animation: "blink 0.8s step-end infinite",
                verticalAlign: "text-bottom",
              }} />
            )}
          </>
        ) : streaming ? (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            color: "var(--text-secondary, #8B8FA3)",
            fontSize: 13,
          }}>
            <span style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              background: color,
              animation: "blink 1s ease infinite",
            }} />
            Генерирую интерпретацию...
          </div>
        ) : null}
      </div>
    </div>
  );
}
