package de.merkweiser.notify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Ein geplanter Alarm ist fällig: Benachrichtigung zeigen und aus der Ablage entfernen. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra(NotifyStore.EXTRA_ID, 0)
        NotifyStore.show(context, id, intent.getStringExtra(NotifyStore.EXTRA_TITLE) ?: "Merkweiser",
            intent.getStringExtra(NotifyStore.EXTRA_BODY) ?: "", intent.getStringExtra(NotifyStore.EXTRA_LEVEL) ?: "normal")
        NotifyStore.removeShown(context, id, intent.getLongExtra(NotifyStore.EXTRA_AT, 0L))
    }
}
