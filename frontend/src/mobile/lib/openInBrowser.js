/**
 * openInBrowser.js — единственная точка, где приложение открывает системный
 * браузер (SPEC_MORE_SCREEN.md §4.3). Используется дважды: кнопка «Тарифы»
 * и ссылка на выгрузку данных в личном кабинете сайта (§6.2).
 *
 * `window.open()` не годится — его поведение внутри Android WebView в этом
 * проекте не проверено, а `@capacitor/browser` даёт прямой системный вызов.
 */

import { Browser } from '@capacitor/browser';

export function openInBrowser(url) {
  return Browser.open({ url });
}
