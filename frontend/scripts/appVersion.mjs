/**
 * appVersion.mjs — номер версии приложения, один на всю сборку.
 *
 * `0.1.0-412`: версия из package.json и номер прогона «Mobile APK» в CI
 * (GITHUB_RUN_NUMBER) — решение владельца 29.09.2026. Номер прогона растёт сам,
 * поэтому versionCode не нужно поднимать руками, а сборки различаются по номеру,
 * который видно в «Настройках» и в подписи к APK.
 *
 * Берут ДВА места, и числа обязаны совпадать: `vite.config.mobile.js` (строка
 * версии в бандле → экран «Настройки» и Sentry) и `patch-android.mjs`
 * (versionCode/versionName в build.gradle). Поэтому функция здесь, а не
 * литералом в каждом.
 *
 * ⚠️ GITHUB_RUN_NUMBER считается ОТДЕЛЬНО для каждого workflow. Переименование
 * mobile-build.yml или перенос сборки в другой workflow начнёт счёт с 1, и
 * versionCode пойдёт вниз — Android откажется ставить такой APK поверх
 * установленного («пакет конфликтует»), а RuStore/Google Play не примут. Если
 * сборка переезжает — прибавлять к номеру смещение, а не обнулять.
 *
 * Локально номера нет: versionName — голая версия, versionCode не трогается.
 */
export function appVersion(pkgVersion, runNumber = process.env.GITHUB_RUN_NUMBER) {
  const run = Number.parseInt(runNumber || '', 10);
  if (!Number.isInteger(run) || run <= 0) return { name: pkgVersion, code: null };
  return { name: `${pkgVersion}-${run}`, code: run };
}
