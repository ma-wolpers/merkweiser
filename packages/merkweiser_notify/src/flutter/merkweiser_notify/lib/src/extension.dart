import 'package:flet/flet.dart';

import 'notify_service.dart';

/// Registriert den Service „MerkweiserNotify“ (Python: merkweiser_notify.MerkweiserNotify).
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "MerkweiserNotify":
        return MerkweiserNotifyService(control: control);
      default:
        return null;
    }
  }
}
