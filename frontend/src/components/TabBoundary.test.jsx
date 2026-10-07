// Упавшая вкладка не роняет ChartPage (#123: ReferenceError во вкладке
// транзитов давал белый экран). jsdom в проекте нет — react-test-renderer.
import { describe, expect, it, vi } from 'vitest';
import { act, create } from 'react-test-renderer';
import TabBoundary from './TabBoundary';

let broken = true;
function Tab() {
  if (broken) throw new ReferenceError('showPaywall is not defined');
  return <p>вкладка</p>;
}

function Page({ tab }) {
  return (
    <main>
      <header>шапка</header>
      <TabBoundary key={tab}><Tab /></TabBoundary>
    </main>
  );
}

const text = (r) => JSON.stringify(r.toJSON());

describe('TabBoundary', () => {
  it('падающая вкладка — страница на месте, заглушка, «Повторить» перерисовывает', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    let r;
    act(() => { r = create(<Page tab="transits" />); });

    expect(text(r)).toContain('шапка');
    expect(text(r)).toContain('Не удалось показать этот раздел.');

    broken = false;
    const retry = r.root.find((n) => n.props.onClick && JSON.stringify(n.props.children) === '"Повторить"');
    act(() => retry.props.onClick());
    expect(text(r)).toContain('вкладка');
    expect(text(r)).not.toContain('Не удалось');
  });

  it('смена вкладки сбрасывает границу', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    broken = true;
    let r;
    act(() => { r = create(<Page tab="transits" />); });
    expect(text(r)).toContain('Не удалось');

    broken = false;
    act(() => r.update(<Page tab="chart" />));
    expect(text(r)).toContain('вкладка');
  });
});
