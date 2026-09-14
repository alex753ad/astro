import { useState } from 'react';

/**
 * Поле пароля с переключателем показа. Один компонент на все формы:
 * веб (inline style) и мобильные экраны (className="mobile-input") —
 * отличаются только пропсами, разметка обёртки и кнопки общая.
 * Образец — AuthModal.jsx, там глаз был первым и остаётся на месте.
 */
export default function PasswordInput({ style, ...props }) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <input {...props} type={show ? 'text' : 'password'}
        style={{ paddingRight: 40, ...style }} />
      {/* type="button" обязателен: внутри <form> кнопка без него отправит форму */}
      <button type="button" onClick={() => setShow(s => !s)} tabIndex={-1}
        aria-label={show ? 'Скрыть пароль' : 'Показать пароль'}
        style={{
          position: 'absolute', right: 10, top: '50%',
          transform: 'translateY(-50%)', background: 'none',
          border: 'none', cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1,
        }}>
        {show ? '🙈' : '👁'}
      </button>
    </div>
  );
}
