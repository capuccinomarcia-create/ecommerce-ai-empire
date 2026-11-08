"""Autenticação local: hash scrypt, sem senha em texto e sem token público.

Para produção com múltiplos usuários, use o Supabase Auth (database/schema.sql
já tem a tabela ``users`` e as políticas de RLS). Esta implementação local
cobre o caso de uso do proprietário único, com senha forte guardada apenas
como hash.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32


def hash_password(password: str) -> str:
    """Formato: scrypt$n$r$p$salt_b64$hash_b64"""
    if not password or len(password) < 8:
        raise ValueError("a senha precisa ter pelo menos 8 caracteres")
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_LEN
    )
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(derived).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(hash_b64)),
        )
        return hmac.compare_digest(derived, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


class AuthService:
    """Usuários no banco; nenhuma senha é exposta pela API ou pelo painel."""

    def __init__(self, repo):
        self.repo = repo

    def has_users(self) -> bool:
        return self.repo.count("users") > 0

    def create_user(self, email: str, password: str, full_name: str = "",
                    role: str = "owner") -> dict[str, Any]:
        if self.repo.find_one("users", {"email": email}):
            raise ValueError("e-mail já cadastrado")
        user = self.repo.insert(
            "users",
            {
                "email": email.strip().lower(),
                "full_name": full_name or email.split("@")[0],
                "role": role,
                "password_hash": hash_password(password),
            },
        )
        user.pop("password_hash", None)
        return user

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.repo.find_one("users", {"email": (email or "").strip().lower()})
        if not user:
            return None
        if not verify_password(password, user.get("password_hash") or ""):
            return None
        public = {k: v for k, v in user.items() if k != "password_hash"}
        return public

    def change_password(self, email: str, current: str, new: str) -> bool:
        if not self.authenticate(email, current):
            return False
        user = self.repo.find_one("users", {"email": email.strip().lower()})
        self.repo.update("users", user["id"], {"password_hash": hash_password(new)})
        return True
