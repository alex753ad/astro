/**
 * MotionButton — motion-обёртка над <button> без навязанного внешнего вида.
 * См. DESIGN_SYSTEM.md §5 Button / §6 B2.
 */

import { motion, useReducedMotion } from 'framer-motion';

const LEVELS = {
  primary: {
    hover: { y: -3, boxShadow: 'var(--shadow-accent)' },
    tap: { scale: 0.95 },
  },
  secondary: {
    hover: { y: -1, boxShadow: 'var(--shadow-card)' },
    tap: { scale: 0.97 },
  },
  ghost: {
    hover: {},
    tap: { scale: 0.98 },
  },
};

export default function MotionButton({ level = 'primary', disabled, children, ...props }) {
  const prefersReduced = useReducedMotion();
  const { hover, tap } = LEVELS[level] || LEVELS.primary;
  const motionEnabled = !disabled && !prefersReduced;

  return (
    <motion.button
      {...props}
      disabled={disabled}
      whileHover={motionEnabled ? hover : undefined}
      whileTap={motionEnabled ? tap : undefined}
      transition={{
        y: { duration: 0.2 },
        boxShadow: { duration: 0.2 },
        scale: { type: 'spring', stiffness: 90 },
      }}
    >
      {children}
    </motion.button>
  );
}
