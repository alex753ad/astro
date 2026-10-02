package ru.aristeatime.widget;

import android.content.Context;
import android.content.SharedPreferences;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Запас дней, который кладёт приложение, и выбор сегодняшнего. */
final class WidgetData {

    static final class Day {
        String day;     // «2 октября»
        String phase;   // «убывающая Луна»
        String title;   // «15:01 · Луна к твоей Венере» или фаза
        String advice;  // совет; пусто — строки нет
        double elong;   // элонгация Луны, 0…360 — по ней рисуется картинка
        boolean stored; // из запаса, а не запасной вариант
    }

    private static final String PREFS = "aristea_widget";
    private static final String KEY = "data";

    // Подписи фаз — как story_card.PHASES на сервере (по 45° с центром на 0°).
    private static final String[] PHASES = {
        "новолуние", "растущий серп", "первая четверть", "растущая Луна",
        "полнолуние", "убывающая Луна", "последняя четверть", "убывающий серп",
    };
    // Совет фазы — копия backend/widget.py PHASE_ADVICE в порядке PHASES
    // (таблица docs/widget_phase_texts.md, согласована владельцем 02.10.2026).
    // Совпадение строк держит backend/tests/test_widget.py.
    private static final String[] PHASE_ADVICE = {
        "Тихий день: подумай, что хочешь начать.",
        "Сделай первый маленький шаг к задуманному.",
        "Не бросай начатое на первой трудности.",
        "Доведи до ума то, что уже в работе.",
        "Посмотри, что уже получилось, и порадуйся этому.",
        "Поделись тем, что знаешь, с тем, кому это пригодится.",
        "Откажись от одного лишнего: вещи, дела или обещания.",
        "Отдохни и не бери на себя новых дел.",
    };
    private static final String[] MONTHS = {
        "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
        "августа", "сентября", "октября", "ноября", "декабря",
    };

    private WidgetData() {}

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static void save(Context c, String json) {
        prefs(c).edit().putString(KEY, json == null ? "" : json).apply();
    }

    /**
     * Что показать сегодня (решение владельца 02.10.2026):
     *   · в запасе есть сегодняшний день — событие и совет (флаг включён);
     *   · запас есть, но кончился — «Открой Аристею, чтобы обновить день»:
     *     только здесь открытие приложения что-то меняет;
     *   · вышли из аккаунта при включённом флаге — «Войди…»;
     *   · иначе (флаг выключен, приложение не открывали, нет карты) — фаза
     *     Луны и совет фазы, посчитанные на телефоне.
     * Дата — по часам телефона, а сервер считал дни в поясе аккаунта: в
     * поездке со сменой пояса возможен сдвиг на сутки около полуночи
     * (принято владельцем 02.10.2026, docs/widget_plan.md).
     */
    static Day today(Context c) {
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        boolean signedOut = false;
        boolean stale = false;
        try {
            JSONObject o = new JSONObject(prefs(c).getString(KEY, ""));
            signedOut = o.optBoolean("signedOut");
            JSONArray days = o.optJSONArray("days");
            stale = days != null && days.length() > 0;
            for (int i = 0; days != null && i < days.length(); i++) {
                JSONObject x = days.getJSONObject(i);
                if (!today.equals(x.optString("date"))) continue;
                Day d = new Day();
                d.day = x.optString("day");
                d.phase = x.optString("phase");
                d.title = x.optString("title");
                d.advice = x.optString("advice");
                d.elong = x.optDouble("elong", Moon.approxElongation(System.currentTimeMillis()));
                d.stored = true;
                return d;
            }
        } catch (JSONException ignored) {
            // пусто ("" — флаг выключен или приложение не открывали) или битое
        }
        return local(signedOut, stale);
    }

    /** Сколько дней в запасе — для строки диагностики. */
    static int count(Context c) {
        try {
            JSONArray days = new JSONObject(prefs(c).getString(KEY, "")).optJSONArray("days");
            return days == null ? 0 : days.length();
        } catch (JSONException e) {
            return 0;
        }
    }

    /** Без запаса на сегодня: Луна считается на телефоне и остаётся верной. */
    private static Day local(boolean signedOut, boolean stale) {
        Calendar now = Calendar.getInstance();
        Day d = new Day();
        d.elong = Moon.approxElongation(now.getTimeInMillis());
        d.day = now.get(Calendar.DAY_OF_MONTH) + " " + MONTHS[now.get(Calendar.MONTH)];
        int phase = (int) (((d.elong + 22.5) % 360) / 45);
        d.phase = PHASES[phase];
        // Тексты — docs/widget_phase_texts.md (ветка wip/tariffs-pdf).
        if (signedOut) {
            d.title = "Войди, чтобы видеть свой день";
            d.advice = "";
        } else if (stale) {
            d.title = "Открой Аристею, чтобы обновить день";
            d.advice = "";
        } else {
            d.title = d.phase.substring(0, 1).toUpperCase(new Locale("ru")) + d.phase.substring(1);
            d.advice = PHASE_ADVICE[phase];
        }
        return d;
    }
}
