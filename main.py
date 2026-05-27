import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup
from dingtalkchatbot.chatbot import DingtalkChatbot


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
DEFAULT_REQUEST_URL = "https://application.xiaofubao.com/app/electric/queryISIMSRoomSurplus"
REQUIRED_ROOM_FIELDS = ("areaId", "buildingCode", "floorCode", "roomCode", "platform")


@dataclass
class AppConfig:
    webhook: str
    secret: str
    request_address: str
    request_timeout: int
    request_cookie: str
    request_headers: dict[str, str]
    data_student_room: dict[str, Any]
    save_last_response: bool
    low_threshold: float
    notify_only_when_low: bool


@dataclass
class ElectricityResult:
    text: str
    surplus: float
    amount: float | None = None
    room: str | None = None


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"未找到配置文件: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    headers = raw.get("request_headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("request_headers 必须是 YAML 对象")

    return AppConfig(
        webhook=str(raw.get("webhook") or "").strip(),
        secret=str(raw.get("secret") or "").strip(),
        request_address=str(raw.get("request_address") or DEFAULT_REQUEST_URL).strip(),
        request_timeout=int(raw.get("request_timeout") or 15),
        request_cookie=str(raw.get("request_cookie") or "").strip(),
        request_headers={str(k): str(v) for k, v in headers.items() if v not in (None, "")},
        data_student_room=raw.get("data_studentRoom") or {},
        save_last_response=bool(raw.get("save_last_response", False)),
        low_threshold=float(raw.get("low_threshold", 10)),
        notify_only_when_low=bool(raw.get("notify_only_when_low", False)),
    )


def validate_room_data(data: dict[str, Any], label: str) -> None:
    missing = [field for field in REQUIRED_ROOM_FIELDS if not data.get(field)]
    if missing:
        raise ValueError(f"{label} 缺少必要参数: {', '.join(missing)}")


def build_headers(config: AppConfig) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/116.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://application.xiaofubao.com",
        "Referer": "https://application.xiaofubao.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    headers.update(config.request_headers)
    if config.request_cookie:
        headers["Cookie"] = config.request_cookie
    return headers


def extract_first_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        return float(match.group()) if match else None
    if isinstance(value, dict):
        for item in value.values():
            number = extract_first_number(item)
            if number is not None:
                return number
    if isinstance(value, list):
        for item in value:
            number = extract_first_number(item)
            if number is not None:
                return number
    return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return extract_first_number(value)


def format_room_name(room_name: Any) -> str | None:
    if not room_name:
        return None
    return re.sub(r"(北宿\d)(\d层)", r"\1 \2", str(room_name))


def parse_json_response(payload: Any) -> ElectricityResult:
    if not isinstance(payload, dict):
        raise ValueError("JSON响应不是对象")

    status_code = payload.get("statusCode")
    if status_code not in (None, 0, "0"):
        raise ValueError(f"接口返回异常: {payload.get('message') or status_code}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("JSON中缺少data对象")

    surplus = to_float(data.get("soc"))
    surplus_list = data.get("surplusList")
    if surplus is None and isinstance(surplus_list, list) and surplus_list:
        first = surplus_list[0]
        if isinstance(first, dict):
            surplus = to_float(first.get("surplus") or first.get("totalSurplus"))

    if surplus is None:
        raise ValueError("JSON中未找到明确的电量字段")

    room_name = format_room_name(data.get("displayRoomName") or data.get("roomName"))
    amount = to_float(data.get("totalSocAmount") or data.get("amount"))
    text = f"{surplus:g} 度" + (f" ({room_name})" if room_name else "")
    return ElectricityResult(text=text, surplus=surplus, amount=amount, room=room_name)


def parse_html_response(text: str) -> ElectricityResult | None:
    soup = BeautifulSoup(text, "lxml")
    element = soup.find("span", class_="font-16 elet-num")
    if not element:
        return None

    display_text = element.text.strip()
    surplus = extract_first_number(display_text)
    if surplus is None:
        raise ValueError("HTML响应中未找到电量数字")
    return ElectricityResult(text=display_text, surplus=surplus)


def save_response(label: str, response: requests.Response) -> None:
    suffix = "json" if "json" in response.headers.get("content-type", "").lower() else "txt"
    target = BASE_DIR / f"last_response_{label}.{suffix}"
    target.write_text(response.text, encoding="utf-8")


def query_electricity(
    session: requests.Session,
    config: AppConfig,
    room_data: dict[str, Any],
    label: str,
) -> ElectricityResult:
    validate_room_data(room_data, label)
    headers = build_headers(config)

    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            response = session.post(
                config.request_address,
                data=room_data,
                headers=headers,
                timeout=config.request_timeout,
            )
            response.raise_for_status()
            if config.save_last_response:
                save_response(label, response)

            html_result = parse_html_response(response.text)
            if html_result:
                return html_result
            return parse_json_response(response.json())
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                print(f"{label} 请求失败，1秒后重试: {exc}")
                time.sleep(1)
        except ValueError:
            raise

    raise RuntimeError(f"{label} 请求失败: {last_error}")


def send_message(config: AppConfig, msg: str, alarm: bool = False) -> None:
    print(msg)
    if not config.webhook:
        print("未配置 webhook，已跳过钉钉发送")
        return
    if not config.webhook.startswith(("http://", "https://")):
        print("webhook 格式不正确，已跳过钉钉发送")
        return

    try:
        bot = DingtalkChatbot(config.webhook, secret=config.secret)
        print(bot.send_text(msg=msg, is_at_all=alarm))
    except Exception as exc:
        print("消息发送失败:", exc)


def build_report(now: str, student: ElectricityResult) -> str:
    return "\n".join([
        f"Time: {now}",
        f"学生房间电量: {student.text}",
    ])


def main() -> None:
    config = load_config()
    try:
        with requests.Session() as session:
            student = query_electricity(session, config, config.data_student_room, "学生房间")

        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        report = build_report(now, student)
        should_alarm = student.surplus < config.low_threshold
        if config.notify_only_when_low and not should_alarm:
            print(report)
            print(f"电量未低于阈值 {config.low_threshold:g} 度，已跳过钉钉推送")
            return
        send_message(config, report + ("\n该充电费了！\n" if should_alarm else ""), alarm=should_alarm)
    except Exception as exc:
        send_message(config, str(exc), alarm=True)


if __name__ == "__main__":
    main()
