import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_hbb/common.dart';
import 'package:flutter_hbb/models/platform_model.dart';
import 'package:get/get.dart';

class LicenseStatus {
  final bool licensed;
  final String reason;
  final String serial;
  final String customer;
  final int expiresAt;
  final int daysLeft;
  final bool expiringSoon;

  LicenseStatus.fromJson(Map<String, dynamic> json)
      : licensed = json['licensed'] == true,
        reason = json['reason'] ?? '',
        serial = json['serial'] ?? '',
        customer = json['customer'] ?? '',
        expiresAt = json['expires_at'] ?? 0,
        daysLeft = json['days_left'] ?? 0,
        expiringSoon = json['expiring_soon'] == true;

  static LicenseStatus load() {
    try {
      return LicenseStatus.fromJson(jsonDecode(bind.mainGetLicenseStatus()));
    } catch (e) {
      debugPrint('license status: $e');
      return LicenseStatus.fromJson({});
    }
  }

  String get expiryText {
    if (expiresAt <= 0) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(expiresAt * 1000);
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(d.day)}/${two(d.month)}/${d.year}';
  }

  String get message {
    if (!licensed) return translate(reason);
    if (expiringSoon) {
      return translate('license-expiring-tip')
          .replaceAll('{}', daysLeft.toString());
    }
    return '${translate('Valid until')} $expiryText';
  }
}

/// The license state on the home page, with the way to activate or renew.
class LicenseCard extends StatefulWidget {
  const LicenseCard({Key? key}) : super(key: key);

  @override
  State<LicenseCard> createState() => _LicenseCardState();
}

class _LicenseCardState extends State<LicenseCard> {
  LicenseStatus _status = LicenseStatus.load();
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _refresh() {
    final status = LicenseStatus.load();
    if (status.licensed != _status.licensed ||
        status.reason != _status.reason ||
        status.expiresAt != _status.expiresAt ||
        status.serial != _status.serial) {
      setState(() => _status = status);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    final warn = !status.licensed || status.expiringSoon;
    final color = !status.licensed
        ? Colors.red
        : (status.expiringSoon ? Colors.orange : Colors.green);
    return Container(
      margin: const EdgeInsets.only(top: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: color.withOpacity(0.6)),
        borderRadius: BorderRadius.circular(8),
        color: color.withOpacity(0.08),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(status.licensed ? Icons.verified : Icons.lock_outline,
                color: color, size: 18),
            const SizedBox(width: 6),
            Expanded(
              child: Text(translate('License'),
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
          ]),
          if (status.customer.isNotEmpty)
            Text(status.customer, style: const TextStyle(fontSize: 12))
                .marginOnly(top: 6),
          Text(status.message, style: const TextStyle(fontSize: 12))
              .marginOnly(top: 6),
          if (warn)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => showLicenseDialog(onDone: _refresh),
                child: Text(translate('Activate license')),
              ),
            ),
        ],
      ),
    );
  }
}

void showLicenseDialog({Function()? onDone}) {
  final current = LicenseStatus.load();
  final controller = TextEditingController(text: current.serial);
  var error = '';
  var busy = false;
  gFFI.dialogManager.show((setState, close, context) {
    submit() async {
      final serial = controller.text.trim();
      if (serial.isEmpty || busy) return;
      setState(() {
        busy = true;
        error = '';
      });
      var reason = 'license-offline-tip';
      try {
        final res = jsonDecode(await bind.mainActivateLicense(serial: serial));
        reason = res['ok'] == true ? '' : (res['reason'] ?? reason);
      } catch (e) {
        debugPrint('license activation: $e');
      }
      setState(() {
        busy = false;
        error = reason;
      });
      if (reason.isEmpty) {
        close();
        onDone?.call();
        showToast(translate('License activated'));
      }
    }

    return CustomAlertDialog(
      title: Text(translate('Activate license')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (current.licensed || current.reason.isNotEmpty)
            Text(current.message).marginOnly(bottom: 12),
          TextField(
            controller: controller,
            autofocus: true,
            textCapitalization: TextCapitalization.characters,
            decoration: InputDecoration(
              labelText: translate('Serial number'),
              hintText: 'XXXX-XXXX-XXXX-XXXX-XXXX',
              errorText: error.isEmpty ? null : translate(error),
              errorMaxLines: 3,
            ),
            onSubmitted: (_) => submit(),
          ).workaroundFreezeLinuxMint(),
          if (busy) const LinearProgressIndicator().marginOnly(top: 12),
        ],
      ),
      actions: [
        dialogButton('Cancel', onPressed: close, isOutline: true),
        dialogButton('Activate', onPressed: busy ? null : submit),
      ],
      onSubmit: submit,
      onCancel: close,
    );
  });
}
