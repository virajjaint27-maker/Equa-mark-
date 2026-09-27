"""Dynamic watermark text variables: {date}, {time}, {user}, {chat}, ..."""
import random
import re
import time

_VAR = re.compile(r"\{(date|time|year|month|day|user|username|chat|count|rand|rand100)\}", re.I)


def resolve(text, user=None, chat=None, count=None):
    """Replace template variables in watermark text at render time."""
    if not text or "{" not in text:
        return text
    now = time.localtime()

    def _sub(m):
        key = m.group(1).lower()
        if key == "date":
            return time.strftime("%d %b %Y", now)
        if key == "time":
            return time.strftime("%H:%M", now)
        if key == "year":
            return time.strftime("%Y", now)
        if key == "month":
            return time.strftime("%b", now)
        if key == "day":
            return time.strftime("%a", now)
        if key == "user":
            if user is not None and getattr(user, "first_name", None):
                return user.first_name
            return "user"
        if key == "username":
            if user is not None and getattr(user, "username", None):
                return "@" + user.username
            return "user"
        if key == "chat":
            if chat is not None and getattr(chat, "title", None):
                return chat.title
            if user is not None and getattr(user, "first_name", None):
                return user.first_name
            return "chat"
        if key == "count":
            return str(count if count is not None else 0)
        if key == "rand":
            return str(random.randint(100000, 999999))
        if key == "rand100":
            return str(random.randint(0, 99))
        return m.group(0)

    return _VAR.sub(_sub, text)
