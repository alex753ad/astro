package ru.aristeatime.widget;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.ResolveInfo;
import android.content.res.XmlResourceParser;
import android.content.pm.PackageManager;
import android.os.Build;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.List;

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

        // То, что видит AppWidgetService, когда ищет провайдеры (02.10.2026:
        // на Samsung SM-G970F «в списке нет» даже после перезагрузки, а на
        // эмуляторе Android 12 тот же APK принимается).
        r.put("all", m.getInstalledProviders().size());   // виджеты всех приложений
        Intent upd = new Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).setPackage(c.getPackageName());
        List<ResolveInfo> rcv = c.getPackageManager().queryBroadcastReceivers(upd, PackageManager.GET_META_DATA);
        r.put("rcv", rcv.size());
        String xml = "нет";
        for (ResolveInfo ri : rcv) {
            if (!cn.getClassName().equals(ri.activityInfo.name)) continue;
            try (XmlResourceParser x = ri.activityInfo.loadXmlMetaData(c.getPackageManager(), AppWidgetManager.META_DATA_APPWIDGET_PROVIDER)) {
                if (x == null) { xml = "null"; break; }
                int ev;
                while ((ev = x.next()) != XmlResourceParser.END_DOCUMENT && ev != XmlResourceParser.START_TAG) { }
                xml = x.getName();
            } catch (Exception e) {
                xml = e.getClass().getSimpleName();
            }
        }
        r.put("xml", xml);
        r.put("ext", (c.getApplicationInfo().flags & ApplicationInfo.FLAG_EXTERNAL_STORAGE) != 0);
        r.put("dev", Build.MANUFACTURER + " " + Build.MODEL + " · Android " + Build.VERSION.RELEASE + " · " + Build.DISPLAY);
        call.resolve(r);
    }
}
