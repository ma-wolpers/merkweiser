package de.merkweiser.notify

import android.Manifest
import android.app.Activity
import android.app.AlarmManager
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry

/**
 * MethodChannel „merkweiser_notify“: Berechtigung, Planen, Stornieren, Status, Start-Payload.
 *
 * Die Payload „heute“ kommt aus dem Start-Intent (Kaltstart) bzw. aus onNewIntent
 * (App lief schon, launchMode singleTop) und wird genau einmal ausgeliefert.
 */
class MerkweiserNotifyPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware,
    PluginRegistry.RequestPermissionsResultListener, PluginRegistry.NewIntentListener {

    private var channel: MethodChannel? = null
    private var context: Context? = null
    private var activity: Activity? = null
    private var binding: ActivityPluginBinding? = null
    private var pendingPermission: MethodChannel.Result? = null
    private var payload: String? = null

    override fun onAttachedToEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        context = flutter.applicationContext
        channel = MethodChannel(flutter.binaryMessenger, "merkweiser_notify").also { it.setMethodCallHandler(this) }
    }

    override fun onDetachedFromEngine(flutter: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        channel = null
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) = attach(binding)
    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) = attach(binding)
    override fun onDetachedFromActivityForConfigChanges() = detach()
    override fun onDetachedFromActivity() = detach()

    private fun attach(b: ActivityPluginBinding) {
        binding = b
        activity = b.activity
        b.addRequestPermissionsResultListener(this)
        b.addOnNewIntentListener(this)
        readPayload(b.activity.intent)
    }

    private fun detach() {
        binding?.removeRequestPermissionsResultListener(this)
        binding?.removeOnNewIntentListener(this)
        binding = null
        activity = null
    }

    override fun onNewIntent(intent: Intent): Boolean {
        readPayload(intent)
        return false
    }

    private fun readPayload(intent: Intent?) {
        val value = intent?.getStringExtra(NotifyStore.EXTRA_PAYLOAD) ?: return
        payload = value
        intent.removeExtra(NotifyStore.EXTRA_PAYLOAD)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val ctx = context ?: return result.error("no_context", "Kein Android-Kontext", null)
        when (call.method) {
            "permission" -> result.success(permission(ctx))
            "request_permission" -> request(ctx, result)
            "schedule" -> {
                val raw = call.argument<List<Map<String, Any?>>>("items") ?: emptyList()
                result.success(NotifyStore.scheduleAll(ctx, raw.map { NotifyStore.Item.from(it) }))
            }
            "cancel_all" -> {
                NotifyStore.cancelAll(ctx)
                result.success(null)
            }
            "status" -> result.success(status(ctx))
            "launch_payload" -> {
                result.success(payload)
                payload = null
            }
            else -> result.notImplemented()
        }
    }

    private fun permission(ctx: Context): String {
        val manager = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val runtime = Build.VERSION.SDK_INT < 33 ||
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        val enabled = Build.VERSION.SDK_INT < 24 || manager.areNotificationsEnabled()
        return if (runtime && enabled) "granted" else "denied"
    }

    private fun request(ctx: Context, result: MethodChannel.Result) {
        val act = activity
        if (Build.VERSION.SDK_INT >= 33 && act != null &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            pendingPermission?.success(permission(ctx))
            pendingPermission = result
            act.requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_CODE)
        } else {
            result.success(permission(ctx))
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>,
                                            grantResults: IntArray): Boolean {
        if (requestCode != REQUEST_CODE) return false
        val ctx = context
        pendingPermission?.success(if (ctx != null) permission(ctx) else "denied")
        pendingPermission = null
        return true
    }

    private fun status(ctx: Context): Map<String, Any> {
        val alarms = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val power = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        val now = System.currentTimeMillis()
        return mapOf(
            "permission" to permission(ctx),
            "pending" to NotifyStore.load(ctx).count { it.at > now },
            "exact_allowed" to (Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()),
            "battery_unrestricted" to (Build.VERSION.SDK_INT < 23 || power.isIgnoringBatteryOptimizations(ctx.packageName)),
            "delivered" to NotifyStore.delivered(ctx),
        )
    }

    companion object {
        private const val REQUEST_CODE = 4711
    }
}
