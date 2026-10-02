package ru.aristeatime.widget;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Мост приложения к виджету «День» (mobile/lib/widgetSync.js).
 *
 * Виджет сам в сеть не ходит: приложение кладёт ему запас дней (save), а
 * флаг widget с сервера включает и выключает сам компонент (setEnabled).
 * Почему так — backend/widget.py.
 */
@CapacitorPlugin(name = "AristeaWidget")
public class WidgetPlugin extends Plugin {

    /** data — JSON {"days": [...]} из /api/v1/widget, {"signedOut": true} или "". */
    @PluginMethod
    public void save(PluginCall call) {
        WidgetData.save(getContext(), call.getString("data", ""));
        DayWidgetProvider.updateAll(getContext());
        call.resolve();
    }

    /**
     * Выключенный компонент пропадает из списка виджетов, а уже стоящий на
     * экране лаунчер убирает (на части лаунчеров — плашка «Виджет
     * недоступен»). ⚠️ Звать только по ответу сервера, а не по «флагов ещё
     * нет»: иначе каждый запуск без сети снимал бы виджет с экрана.
     */
    @PluginMethod
    public void setEnabled(PluginCall call) {
        Context c = getContext();
        int want = Boolean.TRUE.equals(call.getBoolean("enabled", false))
                ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED
                : PackageManager.COMPONENT_ENABLED_STATE_DISABLED;
        ComponentName cn = new ComponentName(c, DayWidgetProvider.class);
        PackageManager pm = c.getPackageManager();
        if (pm.getComponentEnabledSetting(cn) != want) {
            pm.setComponentEnabledSetting(cn, want, PackageManager.DONT_KILL_APP);
        }
        call.resolve();
    }

    /**
     * Компонент включён, а системе виджет не виден («в списке нет»). Так было
     * на Samsung SM-G970F, Android 12, 02.10.2026: прошивка не подхватывает
     * включение с DONT_KILL_APP, хотя на чистом Android 12 (эмулятор) то же
     * включение даёт провайдер за 3 с, а включение с перезапуском процесса
     * (`pm enable`) работает везде.
     *
     * Поэтому: выключить без перезапуска и включить С ПЕРЕЗАПУСКОМ (флаг 0).
     * ⚠️ Процесс приложения после этого вызова убит — ответа JS не дождётся.
     * Звать только из фона (widgetSync.js, visibilitychange → hidden): тогда
     * человек ничего не видит, при следующем открытии — обычный холодный старт.
     */
    @PluginMethod
    public void reenable(PluginCall call) {
        Context c = getContext();
        ComponentName cn = new ComponentName(c, DayWidgetProvider.class);
        PackageManager pm = c.getPackageManager();
        pm.setComponentEnabledSetting(cn, PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP);
        call.resolve();
        pm.setComponentEnabledSetting(cn, PackageManager.COMPONENT_ENABLED_STATE_ENABLED, 0);
    }

    /**
     * Строка диагностики в «Ещё» (нажатие на версию). Разделяет «приложение
     * не включило компонент» и «включило, но система/лаунчер его не видит»:
     * component — 0 по манифесту (выключен), 1 включён, 2 выключен вызовом;
     * listed — провайдер есть у AppWidgetManager, то есть в списке виджетов.
     */
    @PluginMethod
    public void status(PluginCall call) {
        Context c = getContext();
        ComponentName cn = new ComponentName(c, DayWidgetProvider.class);
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        boolean listed = false;
        for (AppWidgetProviderInfo i : m.getInstalledProviders()) {
            if (cn.equals(i.provider)) listed = true;
        }
        JSObject r = new JSObject();
        r.put("component", c.getPackageManager().getComponentEnabledSetting(cn));
        r.put("listed", listed);
        r.put("placed", m.getAppWidgetIds(cn).length);
        r.put("pin", Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && m.isRequestPinAppWidgetSupported());
        r.put("days", WidgetData.count(c));
        r.put("today", WidgetData.today(c).stored);
        call.resolve(r);
    }
}
