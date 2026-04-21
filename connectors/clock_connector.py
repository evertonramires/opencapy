import time

def get_time(format: str) -> str | int:
    if format == "utc":
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    elif format == "local":
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    elif format == "timestamp":
        return int(time.time())
    else:
        raise ValueError("Invalid time format. Use 'utc', 'local', or 'timestamp'.")