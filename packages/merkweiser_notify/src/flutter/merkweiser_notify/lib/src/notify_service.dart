import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Reicht die Methoden des Python-Service unverändert an das Kotlin-Plugin weiter.
///
/// Argumente und Rückgaben sind einfache Werte (Map, List, String, int, bool),
/// die der Standard-Codec des MethodChannel überträgt.
class MerkweiserNotifyService extends FletService {
  MerkweiserNotifyService({required super.control});

  static const MethodChannel _channel = MethodChannel('merkweiser_notify');

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("MerkweiserNotifyService.$name");
    switch (name) {
      case "permission":
      case "request_permission":
      case "schedule":
      case "cancel_all":
      case "status":
      case "launch_payload":
        return await _channel.invokeMethod(name, args);
      default:
        throw Exception("Unknown MerkweiserNotify method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
