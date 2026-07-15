"""Constants for the CarLinko integration.

Byte offsets below are the shared CarLinko/Chery telemetry blob layout, originally
recovered on a Jaecoo J5 EV and confirmed byte-for-byte on an Omoda E5 (2026-07-14):
battery, range, odometer, 12V, speed, consumption and tyre PSI/temp all matched the
app's own displayed values exactly. Fields marked "tentative" vary with car state but
their meaning isn't confirmed yet — treat them as diagnostic/raw only.
"""

DOMAIN = "carlinko"

CONF_REGION = "region"
DEFAULT_REGION = "sam"

# CarLinko API regions, recovered from libapp.so (cqr-api-<region>.hzhjcl.com /
# wss-cqr-<region>.hzhjcl.com). Order shown to the user in the config flow dropdown.
REGIONS: tuple[str, ...] = ("sam", "sea", "ap", "emea", "me", "naf", "saf", "uzb", "vn")
CONF_VEHICLE_ID = "vehicle_id"
CONF_DEVICE_SN = "device_sn"
CONF_VEHICLE_MODEL = "vehicle_model"
CONF_VEHICLE_BRAND = "vehicle_brand"
CONF_VEHICLE_PLATE = "vehicle_plate"
CONF_VEHICLE_IMG_FRONT = "vehicle_img_front"
CONF_VEHICLE_IMG_SIDE = "vehicle_img_side"
CONF_VEHICLE_IMG_TOP = "vehicle_img_top"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 120
MIN_SCAN_INTERVAL = 30

# App-global request-signing key (same string in every CarLinko install; see
# tools/auth.py in the parent project for provenance).
SIGN_KEY = b"mYj3fzMpn77bir66"

USER_AGENT = "Dart/3.10 (dart:io)"
APP_LOGIN_BODY = {
    "method": "PASSWORD",
    "appType": "APP",
    "osType": "ANDROID",
    "appName": "CarLinko",
    "appVersion": "1.12.0",
    "osVersion": "13",
    "language": "en",
    "timeZone": "Asia/Jakarta",
    "phoneBrand": "Google",
    "phoneModel": "Pixel 7 Pro",
    "md5": "",
    "verifyCode": "",
}
