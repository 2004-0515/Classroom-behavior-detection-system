from __future__ import annotations

from flask_login import UserMixin


class AdminUser(UserMixin):
    def __init__(self, username: str):
        self.id = username
        self.username = username

