"""Constants for the CarLinko integration."""

DOMAIN = "carlinko"

CONF_REGION = "region"
DEFAULT_REGION = "sam"

# CarLinko API regions (cqr-api-<region>.hzhjcl.com), in config-flow dropdown order.
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

# App-global request-signing key (same in every CarLinko install).
SIGN_KEY = b"mYj3fzMpn77bir66"

# Remote-control opcodes for `POST /user/vehicle/remoteControl`'s `data` field.
CMD_STOP_CHARGING = "742701"
CMD_FIND_CAR = "740400"
CMD_LOCK = "740100"
CMD_UNLOCK = "740200"
CMD_LIFTGATE_OPEN = "740300"
CMD_LIFTGATE_CLOSE = "740A00"
CMD_SUNROOF_CLOSE = "740F00"
CMD_SUNROOF_OPEN = "740F01"
CMD_SUNROOF_TILT = "740F02"
CMD_WINDOWS_CLOSE = "740500"
CMD_WINDOWS_OPEN = "740600"
CMD_WINDOWS_VENT = "740E00"
CMD_DEFOG_FRONT_ON = "741201"
CMD_DEFOG_FRONT_OFF = "741200"

# Seat opcodes keyed by SEAT_LEVELS' values in api.py. Left = driver, right = assistant.
CMD_SEAT_HEAT_LEFT: dict[str, str] = {"off": "741500", "low": "741501", "medium": "741502", "high": "741503"}
CMD_SEAT_HEAT_RIGHT: dict[str, str] = {"off": "741600", "low": "741601", "medium": "741602", "high": "741603"}
CMD_SEAT_VENT_LEFT: dict[str, str] = {"off": "741A00", "low": "741A01", "medium": "741A02", "high": "741A03"}
CMD_SEAT_VENT_RIGHT: dict[str, str] = {"off": "741B00", "low": "741B01", "medium": "741B02", "high": "741B03"}
CMD_SEAT_HEAT_REAR_LEFT: dict[str, str] = {"off": "741700", "low": "741701", "medium": "741702", "high": "741703"}
CMD_SEAT_HEAT_REAR_RIGHT: dict[str, str] = {"off": "741900", "low": "741901", "medium": "741902", "high": "741903"}
CMD_SEAT_VENT_REAR_LEFT: dict[str, str] = {"off": "741C00", "low": "741C01", "medium": "741C02", "high": "741C03"}
CMD_SEAT_VENT_REAR_RIGHT: dict[str, str] = {"off": "741E00", "low": "741E01", "medium": "741E02", "high": "741E03"}

CMD_QUICK_HEAT_ON = "741F01"
CMD_QUICK_HEAT_OFF = "741F00"
CMD_QUICK_COOL_ON = "742001"
CMD_QUICK_COOL_OFF = "742000"

# `7411` + 2-hex-digit temperature payload, see CarLinkoClient.set_ac_temperature().
CMD_AC_SET_TEMPERATURE_PREFIX = "7411"

CMD_AC_ON = "741001"
CMD_AC_OFF = "741000"

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
