package ru.aristeatime.widget;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.RemoteViews;
import java.util.Calendar;
import java.util.Locale;

/**
 * Виджет «День» (флаг widget, backend/widget.py): фаза Луны и главное
 * событие дня из запаса, который положило приложение.
 *
 * Смена дня — неточный будильник на 00:01 местного времени телефона
 * (RTC, не будит телефон: сработает, когда экран включат, — виджет до этого
 * всё равно никто не видит). Новых разрешений не нужно. Запасной путь —
 * updatePeriodMillis раз в 3 часа (aristea_widget_info.xml) и системные
 * события в манифесте: перезагрузка, смена времени и пояса, обновление APK.
 */
public class DayWidgetReceiver extends AppWidgetProvider {

    static final String ACTION_MIDNIGHT = "ru.aristeatime.widget.MIDNIGHT";
    // Одна строка на главном экране — 40…100 dp, две — от ~110 dp.
    private static final int SQUARE_MIN_HEIGHT_DP = 110;
    private static final Locale RU = new Locale("ru");

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        updateAll(c);
    }

    @Override
    public void onAppWidgetOptionsChanged(Context c, AppWidgetManager m, int id, Bundle options) {
        render(c, m, id, WidgetData.today(c)); // растянули 4×1 в 2×2 или обратно
    }

    @Override
    public void onReceive(Context c, Intent intent) {
        super.onReceive(c, intent);
        String a = intent.getAction();
        if (a != null && !a.startsWith("android.appwidget.")) updateAll(c);
    }

    @Override
    public void onDisabled(Context c) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        if (am != null) am.cancel(midnightIntent(c));
    }

    static void updateAll(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, DayWidgetReceiver.class));
        if (ids.length == 0) return;
        WidgetData.Day d = WidgetData.today(c);
        for (int id : ids) render(c, m, id, d);
        scheduleMidnight(c);
    }

    private static void render(Context c, AppWidgetManager m, int id, WidgetData.Day d) {
        // В портретной ориентации высота виджета — MAX_HEIGHT (документация AppWidgetManager).
        int h = m.getAppWidgetOptions(id).getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 0);
        boolean square = h >= SQUARE_MIN_HEIGHT_DP;
        RemoteViews v = new RemoteViews(c.getPackageName(),
                square ? R.layout.aristea_widget_square : R.layout.aristea_widget_wide);

        String kicker = square ? d.day : d.day + " · " + d.phase;
        v.setTextViewText(R.id.aristea_widget_kicker, kicker.toUpperCase(RU));
        v.setTextViewText(R.id.aristea_widget_title, d.title);
        boolean noAdvice = d.advice == null || d.advice.isEmpty();
        v.setTextViewText(R.id.aristea_widget_advice, noAdvice ? "" : d.advice);
        v.setViewVisibility(R.id.aristea_widget_advice, noAdvice ? View.GONE : View.VISIBLE);
        // Служебная строка («Открой Аристею, чтобы обновить день») длиннее
        // события — в 4×1 ей отдаётся место совета.
        if (!square) v.setInt(R.id.aristea_widget_title, "setMaxLines", noAdvice ? 2 : 1);

        float density = c.getResources().getDisplayMetrics().density;
        v.setImageViewBitmap(R.id.aristea_widget_moon,
                Moon.draw(Math.round((square ? 42 : 48) * density), d.elong));

        // Нажатие — просто открыть приложение: лента и так открывается на
        // сегодняшнем дне (решение владельца 02.10.2026).
        Intent open = c.getPackageManager().getLaunchIntentForPackage(c.getPackageName());
        if (open != null) {
            v.setOnClickPendingIntent(R.id.aristea_widget_root, PendingIntent.getActivity(
                    c, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        }
        m.updateAppWidget(id, v);
    }

    private static void scheduleMidnight(Context c) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        if (am == null) return;
        Calendar next = Calendar.getInstance();
        next.add(Calendar.DAY_OF_YEAR, 1);
        next.set(Calendar.HOUR_OF_DAY, 0);
        next.set(Calendar.MINUTE, 1);
        next.set(Calendar.SECOND, 0);
        next.set(Calendar.MILLISECOND, 0);
        am.set(AlarmManager.RTC, next.getTimeInMillis(), midnightIntent(c));
    }

    private static PendingIntent midnightIntent(Context c) {
        Intent i = new Intent(c, DayWidgetReceiver.class).setAction(ACTION_MIDNIGHT);
        return PendingIntent.getBroadcast(c, 0, i,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
