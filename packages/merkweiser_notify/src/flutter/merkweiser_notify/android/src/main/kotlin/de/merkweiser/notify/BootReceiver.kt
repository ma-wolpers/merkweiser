package de.merkweiser.notify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Nach Neustart oder App-Update gehen gesetzte Alarme verloren: aus der Ablage neu setzen. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            NotifyStore.rescheduleStored(context)
        }
    }
}
