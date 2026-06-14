from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

# Used to verify against when no user/password hash exists, so the login
# route takes comparable time whether or not the account exists.
DUMMY_PASSWORD_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)
