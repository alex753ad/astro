/**
 * authTransport.js — как refresh-токен ездит между клиентом и сервером.
 *
 * Веб и мобильное приложение делают это по-разному, и разница не косметическая:
 *
 * • Веб — HttpOnly-кука astro_refresh (SameSite=Strict, path=/api/v1/auth).
 *   JS её не видит вовсе, поэтому её не украдёт ни XSS, ни испорченная
 *   npm-зависимость в бандле. Так сделано специально, откатывать нельзя.
 *
 * • Мобильное приложение куку получить НЕ МОЖЕТ. Webview Capacitor открывает
 *   страницу с origin https://localhost и ходит на www.aristeatime.ru — для
 *   браузера это кросс-сайтовый запрос, а SameSite=Strict такую куку не
 *   отдаёт. Без обходного пути пользователя выбрасывало бы из приложения
 *   примерно через час, когда истечёт access-токен, и выглядело бы это как
 *   «приложение само разлогинивается».
 *
 * Поэтому мобильный клиент помечает свои запросы заголовком X-Client-Platform,
 * получает refresh в теле ответа и хранит его в нативном хранилище устройства.
 *
 * ⚠️ Разделение сделано КОНСТАНТОЙ ВРЕМЕНИ СБОРКИ, а не проверкой в рантайме.
 * `import.meta.env.VITE_MOBILE` задаётся только в .env.mobile, который Vite
 * читает исключительно при `--mode mobile`. В веб-сборке выражение сворачивается
 * в `false` ещё до минификации, и весь мобильный код из бандла выпадает. То
 * есть веб физически не может начать вести себя иначе — это свойство сборки, а
 * не дисциплина при чтении кода.
 */

export const IS_MOBILE = import.meta.env.VITE_MOBILE === 'true';

export const MOBILE_CLIENT_HEADER = 'X-Client-Platform';

// Ключ нативного хранилища. Другой, чем LEGACY_REFRESH_KEY в client.js: тот
// подчищает старый localStorage веба, и путать эти два места нельзя.
const NATIVE_REFRESH_KEY = 'astro_refresh_native';

/**
 * Заголовки, помечающие клиента. В вебе — пустой объект, то есть запросы
 * уходят ровно такими же, какими уходили раньше.
 */
export function clientHeaders() {
  return IS_MOBILE ? { [MOBILE_CLIENT_HEADER]: 'mobile' } : {};
}

/**
 * Веб обязан слать куку — в ней весь смысл. Мобильному клиенту слать нечего:
 * 'omit' здесь не оптимизация, а способ не создавать видимость, будто
 * куки-путь на устройстве работает.
 */
export const AUTH_CREDENTIALS = IS_MOBILE ? 'omit' : 'include';

/**
 * Capacitor Preferences — Android SharedPreferences в приватном каталоге
 * приложения.
 *
 * Почему не localStorage: оттуда refresh достаёт любой JS, выполнившийся в
 * webview, — то есть XSS. От этого в вебе специально ушли, и заводить ту же
 * дыру на устройстве бессмысленно.
 *
 * Почему не шифрованное хранилище: на нерутованном устройстве песочница
 * приложения — та же граница защиты, что и Keystore, а реальная утечка тут
 * была бы через резервные копии. Она закрыта иначе — android:allowBackup=false
 * (scripts/patch-android.mjs).
 *
 * Импорт динамический и внутри мобильной ветки: в веб-бандл пакет не должен
 * попадать даже отдельным чанком. Проверяется грепом по dist в CI.
 */
async function preferences() {
  if (!IS_MOBILE) return null;
  const { Preferences } = await import('@capacitor/preferences');
  return Preferences;
}

/**
 * Отказ хранилища обязан оставлять след.
 *
 * ⚠️ До 07.09.2026 здесь стояли пустые `catch {}` — все три функции ниже
 * глотали ошибку целиком. Последствие не в том, что «неудобно отлаживать»:
 * несохранённый refresh даёт РОВНО ТОТ ЖЕ симптом, что и неприсланный
 * сервером, и что и мёртвый таймер, — «поработало минут двадцать и
 * перестало». Три разные причины, один вид снаружи и ни одного признака,
 * по которому их различить. Разбор занял три захода именно поэтому.
 *
 * console — единственный канал, какой есть у приложения на устройстве:
 * экрана для этого нет, а Sentry в мобильную сборку не подключён. Читается
 * через chrome://inspect, вкладка Console.
 */
function storageFailed(action, err) {
  // eslint-disable-next-line no-console
  console.warn(`[auth] нативное хранилище refresh недоступно (${action}):`, err);
}

export async function readRefreshToken() {
  try {
    const store = await preferences();
    if (!store) return null;
    const { value } = await store.get({ key: NATIVE_REFRESH_KEY });
    return value || null;
  } catch (err) {
    // Поведение прежнее — ведём себя как «токена нет»: пользователь войдёт
    // заново, а не получит белый экран. Но теперь об этом остаётся запись:
    // «токена нет» и «хранилище отказало» снаружи неразличимы, а чинятся
    // по-разному.
    storageFailed('чтение', err);
    return null;
  }
}

/**
 * Сохраняет refresh из ответа сервера. Вызывать ПОСЛЕ каждого успешного
 * логина и каждого обновления: сервер ротирует refresh, и старый мгновенно
 * становится мёртвым — не перезаписав его, приложение разлогинится на
 * следующем обновлении.
 */
export async function rememberRefreshToken(data) {
  try {
    const store = await preferences();
    if (!store || !data?.refresh_token) return false;
    await store.set({ key: NATIVE_REFRESH_KEY, value: data.refresh_token });
    return true;
  } catch (err) {
    // Возвращаем false, а не бросаем: обновление уже состоялось на сервере,
    // ронять из-за хранилища нечего. Но вызывающий обязан иметь возможность
    // отличить «записали» от «не записали» — до этой правки не мог никто.
    storageFailed('запись', err);
    return false;
  }
}

export async function forgetRefreshToken() {
  try {
    const store = await preferences();
    if (!store) return;
    await store.remove({ key: NATIVE_REFRESH_KEY });
  } catch (err) {
    storageFailed('удаление', err);
  }
}

/**
 * Тело запроса к /refresh и /logout.
 *
 * В вебе — `{}`, ровно как раньше: сервер возьмёт токен из куки. На устройстве
 * — сохранённый refresh, иначе серверу неоткуда его взять и /logout погасит
 * только access, оставив refresh живым на неделю.
 */
export async function authRequestBody() {
  const token = await readRefreshToken();
  return JSON.stringify(token ? { refresh_token: token } : {});
}
