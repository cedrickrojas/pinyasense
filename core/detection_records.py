"""Local detection persistence shared by image, batch, video, and history views."""
import json
import os
from datetime import datetime
from core.json_storage import write_json_atomic


def detection_datetime(value):
    """Read current ISO timestamps and legacy YYYYMMDD_HHMMSS filenames."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or '').strip()
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            parsed = None
            for format_string in ('%Y%m%d_%H%M%S_%f', '%Y%m%d_%H%M%S'):
                try:
                    parsed = datetime.strptime(text, format_string)
                    break
                except ValueError:
                    continue
    if parsed is not None and parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def load_local_results(folder, user_id=None):
    """Staff see their own records; administrators can read legacy unowned files."""
    if not os.path.isdir(folder):
        return []
    results = []
    for filename in sorted(os.listdir(folder), reverse=True):
        if not filename.endswith('_result.json'):
            continue
        try:
            with open(os.path.join(folder, filename), encoding='utf-8-sig') as stream:
                result = json.load(stream)
            if not isinstance(result, dict) or not result.get('disease') or result.get('error'):
                continue
            if user_id is not None and result.get('user_id') != user_id:
                continue
            result.setdefault('filename', filename)
            results.append(result)
        except (OSError, ValueError):
            continue
    results.sort(key=lambda row: detection_datetime(row.get('timestamp')) or datetime.min, reverse=True)
    return results


def save_local_result(folder, result):
    """Atomically save a complete result under its unique record identifier."""
    os.makedirs(folder, exist_ok=True)
    filename = result['record_id'] + '_result.json'
    write_json_atomic(os.path.join(folder, filename), result)
    return filename
