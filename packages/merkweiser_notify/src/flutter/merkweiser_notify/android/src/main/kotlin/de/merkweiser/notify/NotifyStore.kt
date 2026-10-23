package de.merkweiser.notify

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

/**
 * Geplante Benachrichtigungen: Ablage (SharedPreferences, für den Neustart), Alarme und Anzeige.
 *
 * Alarme sind bewusst ungenau (setAndAllowWhileIdle, kein Exact-Alarm-Recht nötig);
 * Android kann sie bei Akkusparen bzw. selten genutzten Apps verzögern.
 */
object NotifyStore {
    private const val PREFS = "merkweiser_notify"
    private const val KEY = "plan"
    const val EXTRA_ID = "mw_id"
    const val EXTRA_TITLE = "mw_title"
    const val EXTRA_BODY = "mw_body"
    const val EXTRA_LEVEL = "mw_level"
    const val EXTRA_AT = "mw_at"
    private const val DELIVERED = "delivered"
    const val EXTRA_PAYLOAD = "merkweiser_notify_payload"

    data class Item(val id: Int, val at: Long, val title: String, val body: String, val level: String) {
        fun toJson(): JSONObject = JSONObject().put("id", id).put("at", at).put("title", title)
            .put("body", body).put("level", level)

        companion object {
            fun from(map: Map<String, Any?>): Item = Item(
                (map["id"] as Number).toInt(), (map["at"] as Number).toLong(),
                map["title"]?.toString() ?: "", map["body"]?.toString() ?: "", map["level"]?.toString() ?: "normal")

            fun fromJson(obj: JSONObject): Item = Item(obj.getInt("id"), obj.getLong("at"), obj.getString("title"),
                obj.getString("body"), obj.optString("level", "normal"))
        }
    }

    fun load(ctx: Context): List<Item> {
        val raw = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, "[]") ?: "[]"
        val array = JSONArray(raw)
        return (0 until array.length()).map { Item.fromJson(array.getJSONObject(it)) }
    }

    private fun save(ctx: Context, items: List<Item>) {
        val array = JSONArray()
        items.forEach { array.put(it.toJson()) }
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, array.toString()).apply()
    }

    /** Ersetzt alle geplanten Einträge; liefert die Zahl der in der Zukunft liegenden. */
    fun scheduleAll(ctx: Context, items: List<Item>): Int {
        cancelAll(ctx)
        val future = items.filter { it.at > System.currentTimeMillis() }
        save(ctx, future)
        future.forEach { setAlarm(ctx, it) }
        return future.size
    }

    /** Nach Neustart/Update: gespeicherte, noch ausstehende Alarme neu setzen. */
    fun rescheduleStored(ctx: Context) {
        val future = load(ctx).filter { it.at > System.currentTimeMillis() }
        save(ctx, future)
        future.forEach { setAlarm(ctx, it) }
    }

    fun cancelAll(ctx: Context) {
        val alarms = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        load(ctx).forEach { alarms.cancel(pendingFor(ctx, it)) }
        save(ctx, emptyList())
    }

    fun removeShown(ctx: Context, id: Int, plannedAt: Long) {
        save(ctx, load(ctx).filter { it.id != id })
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val log = JSONArray(prefs.getString(DELIVERED, "[]") ?: "[]")
        log.put(JSONObject().put("id", id).put("geplant", plannedAt).put("gezeigt", System.currentTimeMillis()))
        while (log.length() > 50) log.remove(0)
        prefs.edit().putString(DELIVERED, log.toString()).apply()
    }

    /** Spike-Bericht: zuletzt gezeigte Benachrichtigungen mit Soll- und Ist-Zeit (ms seit 1970). */
    fun delivered(ctx: Context): List<Map<String, Long>> {
        val log = JSONArray(ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(DELIVERED, "[]") ?: "[]")
        return (0 until log.length()).map { i ->
            val o = log.getJSONObject(i)
            mapOf("id" to o.getLong("id"), "geplant" to o.getLong("geplant"), "gezeigt" to o.getLong("gezeigt"))
        }
    }

    private fun pendingFor(ctx: Context, item: Item): PendingIntent {
        val intent = Intent(ctx, AlarmReceiver::class.java)
            .putExtra(EXTRA_ID, item.id).putExtra(EXTRA_TITLE, item.title)
            .putExtra(EXTRA_BODY, item.body).putExtra(EXTRA_LEVEL, item.level).putExtra(EXTRA_AT, item.at)
        return PendingIntent.getBroadcast(ctx, item.id, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun setAlarm(ctx: Context, item: Item) {
        val alarms = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (Build.VERSION.SDK_INT >= 23) {
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, item.at, pendingFor(ctx, item))
        } else {
            alarms.set(AlarmManager.RTC_WAKEUP, item.at, pendingFor(ctx, item))
        }
    }

    private fun channelFor(level: String): String = when (level) {
        "maximal" -> "mw_maximal"
        "hoch" -> "mw_hoch"
        else -> "mw_normal"
    }

    private fun ensureChannels(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val manager = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel("mw_normal", "Morgen-Erinnerung",
            NotificationManager.IMPORTANCE_DEFAULT))
        manager.createNotificationChannel(NotificationChannel("mw_hoch", "Erinnerung (wichtig)",
            NotificationManager.IMPORTANCE_HIGH))
        manager.createNotificationChannel(NotificationChannel("mw_maximal", "Erinnerung (dringend)",
            NotificationManager.IMPORTANCE_HIGH))
    }

    /** Zeigt eine Benachrichtigung; Antippen öffnet die App mit Payload „heute“. */
    @Suppress("DEPRECATION")
    fun show(ctx: Context, id: Int, title: String, body: String, level: String) {
        ensureChannels(ctx)
        val launch = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra(EXTRA_PAYLOAD, "heute")
        }
        val content = launch?.let {
            PendingIntent.getActivity(ctx, id, it, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(ctx, channelFor(level))
        else Notification.Builder(ctx).setPriority(
            if (level == "normal") Notification.PRIORITY_DEFAULT else Notification.PRIORITY_HIGH)
        builder.setSmallIcon(ctx.applicationInfo.icon).setContentTitle(title).setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body)).setAutoCancel(true)
        if (content != null) builder.setContentIntent(content)
        if (level == "maximal") builder.setCategory(Notification.CATEGORY_REMINDER)
        val manager = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(id, builder.build())
    }
}
