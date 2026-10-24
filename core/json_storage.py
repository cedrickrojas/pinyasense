"""Write complete JSON documents without truncating existing records on failure."""
import json
import os
import tempfile


def write_json_atomic(path, data):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder,
                                         suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
