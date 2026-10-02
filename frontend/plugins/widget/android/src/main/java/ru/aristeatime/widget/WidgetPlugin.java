package ru.aristeatime.widget;

import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;
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
}
