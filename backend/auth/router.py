"""Authentication API router.

Endpoints:
  POST /api/v1/auth/register/email/send-code  — шаг 1: отправить OTP на email
  POST /api/v1/auth/register/email/verify     — шаг 2: подтвердить OTP, создать аккаунт
  POST /api/v1/auth/login                     — вход по email + пароль
  POST /api/v1/auth/refresh                   — обновить access token
  POST /api/v1/auth/google                    — Google OAuth
  GET  /api/v1/auth/confirm-email             — подтверждение email по токену (legacy)
  GET  /api/v1/auth/me                        — профиль текущего пользователя
  DELETE /api/v1/auth/me                      — удалить аккаунт
  POST /api/v1/auth/forgot-password           — запросить сброс пароля
  POST /api/v1/auth/reset-password            — сброс пароля по токену
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import string

import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user, is_session_revoked
from backend.auth.jwt import (
    create_email_confirmation_token,
    create_password_reset_token,
    create_token_pair,
    decode_email_confirmation_token,
    decode_password_reset_token,
    decode_token,
    remaining_ttl,
)
from backend.auth import login_guard
from backend.auth.rate_limits import register_send_key
from backend.auth.sse_tickets import issue as issue_sse_ticket
from backend.auth.token_store import deny, is_denied
from backend.limiter import limiter
from backend.auth.oauth import OAuthError, exchange_google_code
from backend.auth.passwords import hash_password, validate_password, verify_password
from backend.config import get_settings
from backend.database import get_db
from backend.log_utils import mask_email
from backend.models import User, Partner
from backend.schemas import (
    GoogleOAuthRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    SendEmailOTPRequest,
    TokenResponse,
    UserProfileResponse,
    VerifyEmailOTPRequest,
)

logger = logging.getLogger("astro.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ═══════════════════════════════════════════════════════════
# OTP — вспомогательные функции
# ═══════════════════════════════════════════════════════════

OTP_TTL = 600        # 10 минут
OTP_RESEND_TTL = 60  # 1 минута между отправками
MAX_OTP_ATTEMPTS = 5

_CONSENT_MISSING_ERROR = (
    "Необходимо подтвердить согласие на обработку персональных данных "
    "и условия оферты."
)

_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _redis_client


def _gen_otp() -> str:
    # secrets, а не random: random.choices — детерминированный Mersenne Twister,
    # его состояние восстанавливается по нескольким наблюдённым выдачам, и коды
    # подтверждения становятся предсказуемыми.
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _otp_key(identifier: str) -> str:
    return f"reg_otp:{identifier}"


def _resend_key(identifier: str) -> str:
    return f"reg_otp_resend:{identifier}"


async def _store_otp(
    r: aioredis.Redis,
    identifier: str,
    code: str,
    hashed_pw: str,
    ref_code: str,
    name: str = "",
    consent: bool = False,
) -> None:
    payload = json.dumps({
        "code": code, "pw": hashed_pw, "ref": ref_code, "name": name,
        "consent": consent, "attempts": 0,
    })
    await r.set(_otp_key(identifier), payload, ex=OTP_TTL)
    await r.set(_resend_key(identifier), "1", ex=OTP_RESEND_TTL)


async def _consume_otp(r: aioredis.Redis, identifier: str, code: str) -> dict:
    """Проверяет OTP: при успехе удаляет из Redis и возвращает данные."""
    raw = await r.get(_otp_key(identifier))
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код устарел. Запросите новый.")

    data = json.loads(raw)

    if data["attempts"] >= MAX_OTP_ATTEMPTS:
        await r.delete(_otp_key(identifier))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Превышено число попыток. Запросите новый код.",
        )

    if data["code"] != code:
        data["attempts"] += 1
        remaining = MAX_OTP_ATTEMPTS - data["attempts"]
        ttl = max(await r.ttl(_otp_key(identifier)), 1)
        await r.set(_otp_key(identifier), json.dumps(data), ex=ttl)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Неверный код. Осталось попыток: {remaining}.",
        )

    await r.delete(_otp_key(identifier))
    return data


# ═══════════════════════════════════════════════════════════
# Refresh-токен: HttpOnly-кука
# ═══════════════════════════════════════════════════════════
#
# Раньше refresh лежал в localStorage и жил 7 дней. localStorage доступен
# любому JS в источнике — то есть и XSS, и скомпрометированной npm-зависимости,
# попавшей в бандл на сборке. Кража refresh давала неделю полного доступа к
# аккаунту, а HttpOnly для него был недостижим в принципе: он ездил в теле.
#
# Path сужен до /api/v1/auth: кука нужна ровно двум ручкам (/refresh и /logout)
# и не должна прикладываться к каждому запросу к API.
# SameSite=Strict: обе ручки вызываются XHR-ом с нашей же страницы, поэтому
# Strict ничего не ломает — включая возврат с Google OAuth и от платёжного
# провайдера, где кросс-сайтовым является только сам переход, а не
# последующий fetch.
REFRESH_COOKIE_NAME = "astro_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"

# ── Мобильный клиент: refresh в теле, а не кукой ──────────────────────────────
#
# Webview Capacitor открывает страницу с origin https://localhost и ходит на
# www.aristeatime.ru. Для браузера это кросс-сайтовый запрос, а кука выше стоит
# с SameSite=Strict — то есть на /refresh и /logout она не отдаётся вообще.
# Access-токен живёт 15 минут, поэтому без обходного пути пользователя
# выбрасывало бы из приложения примерно через час, и выглядело бы это как
# «приложение само разлогинивается».
#
# Ослаблять куку до SameSite=None ради этого нельзя: она защищает веб, где
# пользователей несравнимо больше, а None открывает CSRF-поверхность на обе
# ручки сразу. Поэтому мобильному клиенту refresh отдаётся в теле ответа, и он
# сам хранит его в нативном хранилище устройства (Capacitor Preferences,
# приватный каталог приложения) — не в localStorage, куда дотянется XSS.
#
# Клиент опознаётся ЯВНЫМ заголовком, а не User-Agent и не origin: и то и
# другое подделывается тривиально и меняется само по себе при смене webview
# или домена, то есть завязка на них ломается молча.
#
# Заголовок ничего не «разрешает»: refresh в теле получает тот, кто и так уже
# прошёл аутентификацию и кому в этом же ответе выдан access-токен. Подделка
# заголовка не даёт злоумышленнику ничего, чего у него не было бы без него, —
# она лишь меняет способ доставки токена его собственной сессии.
MOBILE_CLIENT_HEADER = "X-Client-Platform"
MOBILE_CLIENT_VALUE = "mobile"


def _is_mobile_client(request: Request) -> bool:
    """True, если запрос пришёл от мобильного клиента (Capacitor)."""
    return (request.headers.get(MOBILE_CLIENT_HEADER) or "").strip().lower() == MOBILE_CLIENT_VALUE


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        httponly=True,
        # В локальной разработке фронт ходит по http://localhost — Secure-кука
        # туда просто не доедет, и залогиниться станет невозможно.
        secure=not (settings.debug or settings.testing),
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    # Атрибуты обязаны совпадать с теми, что при установке, иначе браузер
    # удалит не ту куку (а точнее — не удалит никакую).
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def _build_token_response(
    user: User,
    email: str,
    response: Response,
    db: Session,
    *,
    echo_refresh_in_body: bool = False,
) -> TokenResponse:
    """Выдаёт пару токенов: access — в теле, refresh — HttpOnly-кукой.

    echo_refresh_in_body=True нужен в двух случаях, и оба обязательные:

    1. Мобильный клиент прислал заголовок X-Client-Platform: mobile. Куку он
       получить не может (SameSite=Strict + кросс-сайтовый origin webview),
       поэтому для него тело — единственный канал доставки refresh.
    2. Старая сборка фронта прислала refresh в теле запроса. Не ответить ей тем
       же — значит разлогинить всех, у кого в момент деплоя открыта вкладка со
       старым бандлом.

    Кука ставится в обоих случаях: она безвредна там, где её некому принять, и
    её отсутствие сломало бы веб.
    """
    tokens = create_token_pair(user.id, email, user.tier, user.token_version or 0)
    _set_refresh_cookie(response, tokens.refresh_token)
    is_partner = db.query(Partner.id).filter(
        Partner.user_id == user.id, Partner.status == "active",
    ).first() is not None
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token if echo_refresh_in_body else None,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user_id=user.id,
        email=email,
        name=user.name,
        tier=user.tier,
        is_admin=bool(user.is_admin),
        is_partner=is_partner,
    )


def _resolve_referrer_id(db: Session, ref_code: str | None) -> str | None:
    if not ref_code:
        return None
    referrer = db.query(User).filter(User.referral_code == ref_code).first()
    return referrer.id if referrer else None


def _create_user(
    db: Session,
    *,
    email: str,
    hashed_pw: str,
    ref_code: str,
    name: str = "",
) -> User:
    referred_by = _resolve_referrer_id(db, ref_code)
    from backend.auth.consent import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION
    from backend.time_utils import utcnow

    user = User(
        email=email,
        hashed_password=hashed_pw,
        name=name or None,
        is_active=True,
        is_email_confirmed=True,  # подтверждён через OTP
        tier="free",
        referred_by=referred_by,
        consent_given_at=utcnow(),
        consent_terms_version=CURRENT_TERMS_VERSION,
        consent_privacy_version=CURRENT_PRIVACY_VERSION,
    )
    db.add(user)
    db.flush()

    try:
        from backend.referrals import generate_referral_code
        user.referral_code = generate_referral_code(db)
    except Exception as exc:
        logger.warning("referral_code generation failed: %s", exc)

    db.commit()
    db.refresh(user)
    return user


# ═══════════════════════════════════════════════════════════
# РЕГИСТРАЦИЯ — EMAIL OTP
# ═══════════════════════════════════════════════════════════

@router.post(
    "/register/email/send-code",
    response_model=MessageResponse,
    summary="Регистрация — отправить OTP на email",
)
@limiter.limit("5/hour", key_func=register_send_key)
async def register_email_send(
    request: Request,
    data: SendEmailOTPRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Отправляет OTP на email.

    Лимит по IP (5/час) — против рассылки писем на чужие адреса: троттлинг
    _resend_key закрывает только повторную отправку на ОДИН адрес, а перебор
    разных адресов в цикле генерировал тысячи писем через Resend (счёт плюс
    попадание домена в спам-листы).

    Ответ одинаков независимо от того, занят адрес или нет: раньше занятый
    отдавал 409, и форма регистрации работала как оракул существования
    аккаунта. Занятому адресу вместо кода уходит письмо-уведомление — это и
    сигнал владельцу, и выравнивание объёма работы между ветками.
    """
    r = await _get_redis()

    # Троттлинг проверяется до ветвления и ключ ставится в обоих случаях:
    # иначе занятый адрес отличался бы отсутствием 429 на повторный запрос.
    if await r.exists(_resend_key(data.email)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Подождите минуту перед повторной отправкой.",
        )

    existing = db.query(User).filter(User.email == data.email).first()

    # Хеширование выполняется в любом случае — bcrypt занимает сотни
    # миллисекунд и иначе разница во времени ответа выдавала бы ветку.
    hashed_pw = hash_password(data.password)
    code = _gen_otp()

    if existing:
        await r.set(_resend_key(data.email), "1", ex=OTP_RESEND_TTL)
        try:
            from backend.email_service import _send, _base, _h2, _p, _btn
            body = (
                _h2("Аккаунт уже существует")
                + _p("Кто-то попытался зарегистрироваться с вашим адресом в "
                     "<strong>Aristea Timeline</strong>. Аккаунт уже создан ранее.")
                + _p("Если это были вы — просто войдите. Если нет — проигнорируйте письмо.")
                + _btn("Войти →", f"{get_settings().frontend_url}/login")
            )
            await _send(
                data.email,
                "Попытка регистрации — Aristea Timeline",
                _base("Аккаунт уже существует", "Вход в аккаунт", body),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Existing-account notice failed for %s: %s", mask_email(data.email), exc)
        logger.info("Registration attempt on existing account: %s", mask_email(data.email))
    else:
        await _store_otp(r, data.email, code, hashed_pw, data.ref_code or "", data.name or "", data.consent)
        from backend.email_service import send_otp_email
        await send_otp_email(data.email, code)
        logger.info("Email OTP sent → %s", mask_email(data.email))

    return MessageResponse(message="Код подтверждения отправлен на почту.")


@router.post(
    "/register/email/verify",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация — подтвердить OTP",
)
async def register_email_verify(
    request: Request,
    response: Response,
    data: VerifyEmailOTPRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    r = await _get_redis()
    otp_data = await _consume_otp(r, data.email, data.code)

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с таким email уже существует.")

    # Второй раз проверяем явно (первый раз — Pydantic-валидатор на шаге 1):
    # защита от рассинхрона, если формат OTP-payload когда-нибудь изменится.
    if not otp_data.get("consent"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _CONSENT_MISSING_ERROR)

    user = _create_user(
        db,
        email=data.email,
        hashed_pw=otp_data["pw"],
        ref_code=otp_data.get("ref", ""),
        name=otp_data.get("name", ""),
    )
    logger.info("New user via email OTP: %s (%s)", mask_email(data.email), user.id)
    return _build_token_response(
        user, data.email, response, db, echo_refresh_in_body=_is_mobile_client(request),
    )


# ═══════════════════════════════════════════════════════════
# РЕГИСТРАЦИЯ — LEGACY (без OTP, для тестов и обратной совместимости)
# ═══════════════════════════════════════════════════════════

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация (legacy, без OTP)",
)
async def register_legacy(
    request: Request,
    response: Response,
    data: RegisterRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Legacy-путь без OTP оставлен только для тестов: в проде закрыт.
    _s = get_settings()
    if not (_s.testing or _s.debug):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists. Аккаунт с таким email уже существует.")

    from backend.auth.consent import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION
    from backend.time_utils import utcnow

    if not data.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _CONSENT_MISSING_ERROR)

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        is_active=True,
        is_email_confirmed=False,
        tier="free",
        consent_given_at=utcnow(),
        consent_terms_version=CURRENT_TERMS_VERSION,
        consent_privacy_version=CURRENT_PRIVACY_VERSION,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("New user via legacy register: %s (%s)", mask_email(data.email), user.id)
    return _build_token_response(
        user, data.email, response, db, echo_refresh_in_body=_is_mobile_client(request),
    )


# ═══════════════════════════════════════════════════════════
# ВХОД
# ═══════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse, summary="Вход по email + пароль")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Лимит по IP не мешает перебору одного аккаунта с ботнета — считаем
    # неудачи ещё и по email.
    if await login_guard.is_locked(data.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Слишком много неудачных попыток входа. Попробуйте позже.",
        )

    user = db.query(User).filter(User.email == data.email).first()
    if user is None or user.hashed_password is None:
        await login_guard.record_failure(data.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials. Неверный email или пароль.")
    if not verify_password(data.password, user.hashed_password):
        await login_guard.record_failure(data.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials. Неверный email или пароль.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован.")

    await login_guard.reset(data.email)
    return _build_token_response(
        user, user.email, response, db, echo_refresh_in_body=_is_mobile_client(request),
    )


# ═══════════════════════════════════════════════════════════
# REFRESH TOKEN
# ═══════════════════════════════════════════════════════════

@router.post("/refresh", response_model=TokenResponse, summary="Обновить access token")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    data: RefreshRequest | None = None,
    astro_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Источник токена — HttpOnly-кука (веб) ИЛИ тело запроса (мобильный клиент
    # и старые сборки фронта).
    #
    # ⚠️ Если удалить чтение из тела: мобильное приложение потеряет возможность
    # обновлять access-токен, и пользователей начнёт выбрасывать из аккаунта
    # примерно через час — при полностью зелёных веб-тестах, потому что в вебе
    # этот путь не используется вовсе. Куку webview не получает: она стоит с
    # SameSite=Strict, а origin приложения (https://localhost) для неё
    # кросс-сайтовый. Подробности — у MOBILE_CLIENT_HEADER выше.
    from_body = bool(data and data.refresh_token)
    raw_refresh = astro_refresh or (data.refresh_token if data else None)
    if not raw_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token отсутствует.")

    try:
        token_data = decode_token(raw_refresh)
    except JWTError:
        # Кука мёртвая — снимаем её, иначе браузер будет слать мусор ещё неделю.
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный refresh token.")

    if token_data.token_type != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ожидается refresh token.")

    # Reuse-detection: если этот refresh уже был отозван (ротирован) — отклоняем.
    from backend.auth.token_store import is_denied
    if await is_denied(token_data.jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token уже использован.")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или заблокирован.")

    # Refresh, выданный до смены пароля / logout-all, не должен выдавать новые
    # access-токены — иначе глобальная ревокация обходится одним запросом.
    if is_session_revoked(user, token_data):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия отозвана.")

    # Ротация: старый refresh отзываем, выдаём новую пару.
    try:
        await deny(token_data.jti, remaining_ttl(token_data.exp))
    except Exception as exc:  # noqa: BLE001
        logger.error("refresh rotation deny failed: %s", exc)

    return _build_token_response(
        user,
        user.email or token_data.email,
        response,
        db,
        echo_refresh_in_body=from_body or _is_mobile_client(request),
    )


_logout_bearer = HTTPBearer(auto_error=True)


@router.post("/logout", response_model=MessageResponse, summary="Выход — отзыв токенов")
async def logout(
    response: Response,
    data: RefreshRequest | None = None,
    astro_refresh: str | None = Cookie(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(_logout_bearer),
) -> MessageResponse:
    """Отзывает текущий access-токен и (если передан) refresh-токен.

    После вызова оба токена перестают работать до истечения их exp.
    """
    try:
        access = decode_token(credentials.credentials)
        await deny(access.jti, remaining_ttl(access.exp))
    except JWTError:
        pass  # некорректный access — отзывать нечего
    except Exception as exc:  # noqa: BLE001
        logger.error("logout deny(access) failed: %s", exc)
    # Refresh из куки (веб) или из тела (мобильный клиент — куки у него нет).
    #
    # ⚠️ Если удалить чтение из тела: выход из мобильного приложения перестанет
    # отзывать refresh на сервере. Токен останется живым до конца своего срока —
    # то есть «вышел из аккаунта» будет означать только очистку памяти
    # устройства, а украденный до выхода токен продолжит работать неделю.
    raw_refresh = astro_refresh or (data.refresh_token if data else None)
    if raw_refresh:
        try:
            refresh = decode_token(raw_refresh)
            await deny(refresh.jti, remaining_ttl(refresh.exp))
        except JWTError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.error("logout deny(refresh) failed: %s", exc)
    # Куку снимаем всегда: даже если токен в ней уже протух, оставлять её в
    # браузере после явного выхода незачем.
    _clear_refresh_cookie(response)
    return MessageResponse(message="Вы вышли из аккаунта.")


# ═══════════════════════════════════════════════════════════
# GOOGLE OAUTH
# ═══════════════════════════════════════════════════════════

@router.post("/google", response_model=TokenResponse, summary="Вход через Google")
async def google_oauth(
    request: Request,
    response: Response,
    data: GoogleOAuthRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        google_user = await exchange_google_code(code=data.code, redirect_uri=data.redirect_uri)
    except OAuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Google OAuth: {exc}")

    # Не доверяем неподтверждённому Google-email: иначе возможен захват/линковка
    # аккаунта на чужой адрес.
    if not google_user.email_verified:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google не подтвердил email этого аккаунта.",
        )

    user = db.query(User).filter(User.email == google_user.email).first()
    if user is None:
        # consent обязателен только тут — при создании НОВОГО аккаунта, не
        # при входе уже существующего. Сегодня этот путь не вызывается ни
        # одной страницей сайта (Google используется только для Google
        # Calendar в планере, не для входа), но раз колонки User.consent_*
        # NOT NULL — эндпоинт обязан оставаться корректным сам по себе.
        if not data.consent:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, _CONSENT_MISSING_ERROR)

        from backend.auth.consent import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION
        from backend.time_utils import utcnow

        user = User(
            email=google_user.email,
            hashed_password=None,
            is_active=True,
            is_email_confirmed=google_user.email_verified,
            google_sub=google_user.sub,
            tier="free",
            # Как и в _create_user (email-регистрация): привязка только на
            # создании аккаунта, задним числом её не восстановить.
            referred_by=_resolve_referrer_id(db, data.ref_code),
            consent_given_at=utcnow(),
            consent_terms_version=CURRENT_TERMS_VERSION,
            consent_privacy_version=CURRENT_PRIVACY_VERSION,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("New OAuth user: %s (%s)", mask_email(google_user.email), user.id)
    elif user.google_sub is None:
        user.google_sub = google_user.sub
        db.commit()

    return _build_token_response(
        user, user.email, response, db, echo_refresh_in_body=_is_mobile_client(request),
    )


# ═══════════════════════════════════════════════════════════
# EMAIL CONFIRMATION (legacy — для старых ссылок)
# ═══════════════════════════════════════════════════════════

@router.get("/confirm-email", response_model=MessageResponse, summary="Подтвердить email по токену")
async def confirm_email(
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        token_data = decode_email_confirmation_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недействительная или истёкшая ссылка.")

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден.")

    # Ссылка суточной давности не должна переживать logout-all / смену пароля.
    if is_session_revoked(user, token_data):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недействительная или истёкшая ссылка.")

    user.is_email_confirmed = True
    db.commit()
    return MessageResponse(message="Email confirmed. Email подтверждён.")


# ═══════════════════════════════════════════════════════════
# ПРОФИЛЬ
# ═══════════════════════════════════════════════════════════

@router.get("/me", response_model=UserProfileResponse, summary="Профиль текущего пользователя")
async def get_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    is_partner = db.query(Partner.id).filter(
        Partner.user_id == user.id, Partner.status == "active",
    ).first() is not None
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        tier=user.tier,
        is_email_confirmed=user.is_email_confirmed,
        is_admin=bool(user.is_admin),
        is_partner=is_partner,
        stripe_customer_id=user.stripe_customer_id,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.delete("/me", response_model=MessageResponse, summary="Удалить аккаунт")
async def delete_account(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    db.delete(user)
    db.commit()
    logger.info("User deleted: %s (%s)", mask_email(user.email), user.id)
    # Аккаунта больше нет — кука с refresh только мешала бы: следующий /refresh
    # получил бы 401 и лишний раз напугал пользователя.
    _clear_refresh_cookie(response)
    return MessageResponse(message="Account deleted. Аккаунт удалён.")


# ═══════════════════════════════════════════════════════════
# SSE-ТИКЕТЫ
# ═══════════════════════════════════════════════════════════

@router.post("/sse-ticket", summary="Одноразовый тикет для EventSource")
async def create_sse_ticket(user: User = Depends(get_current_user)) -> dict:
    """Обменять access-токен на одноразовый тикет для SSE-подключения.

    EventSource не умеет слать Authorization, а класть в query сам access-токен
    небезопасно (логи прокси, Referer, история). Тикет живёт ~минуту и гасится
    при первом использовании.
    """
    ticket = await issue_sse_ticket(user.id)
    return {"ticket": ticket, "expires_in": get_settings().sse_ticket_ttl_seconds}


# ═══════════════════════════════════════════════════════════
# СБРОС ПАРОЛЯ
# ═══════════════════════════════════════════════════════════

from pydantic import BaseModel as _BM


class ForgotPasswordRequest(_BM):
    email: str


class ResetPasswordRequest(_BM):
    token: str
    new_password: str


@router.post("/forgot-password", response_model=MessageResponse, summary="Запросить сброс пароля")
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = db.query(User).filter(User.email == data.email).first()
    if user and user.hashed_password:
        token = create_password_reset_token(user.id, user.email, user.token_version or 0)
        reset_url = f"{get_settings().frontend_url}/reset-password?token={token}"
        try:
            from backend.email_service import _send, _base, _h2, _p, _btn
            body = (
                _h2("Сброс пароля")
                + _p("Вы запросили сброс пароля для аккаунта <strong>Aristea Timeline</strong>.")
                + _p("Ссылка действительна <strong>1 час</strong>. Если не запрашивали — проигнорируйте.")
                + _btn("Сбросить пароль →", reset_url)
            )
            await _send(
                data.email,
                "Сброс пароля — Aristea Timeline",
                _base("Сброс пароля", "Ссылка для сброса", body),
            )
        except Exception as exc:
            logger.error("Password reset email failed for %s: %s", mask_email(data.email), exc)
        logger.info("Password reset requested: %s", mask_email(data.email))
    return MessageResponse(message="Если аккаунт существует, письмо отправлено.")


@router.post("/reset-password", response_model=MessageResponse, summary="Сбросить пароль")
async def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        token_data = decode_password_reset_token(data.token)
    except JWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или истёкла.")

    # Ссылка одноразовая: повторный переход по уже использованной — как по истёкшей.
    if await is_denied(token_data.jti):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или истёкла.")

    # Та же политика, что и при регистрации: раньше сброс проверял только
    # длину и «только цифры», поэтому мимо него проходили пароли, которые
    # форма регистрации отклоняла.
    try:
        validate_password(data.new_password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден.")

    # Ссылка, выписанная до logout-all или до предыдущей смены пароля, больше не
    # действует: иначе старое письмо оставалось рабочим ключом к аккаунту.
    if is_session_revoked(user, token_data):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или истёкла.")

    user.hashed_password = hash_password(data.new_password)
    # Смена пароля отзывает все ранее выданные access/refresh токены: иначе
    # угнавший сессию сохранял бы доступ и после того, как владелец сменил пароль.
    user.token_version = (user.token_version or 0) + 1
    db.commit()

    # Гасим ссылку только после успешной смены пароля.
    await deny(token_data.jti, remaining_ttl(token_data.exp))

    logger.info("Password reset completed: %s (%s)", mask_email(user.email), user.id)
    return MessageResponse(message="Пароль успешно изменён.")


@router.post("/logout-all", response_model=MessageResponse, summary="Выйти на всех устройствах")
async def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Отзывает все выданные ранее токены пользователя.

    Текущий access-токен тоже перестаёт работать — клиенту нужно войти заново.
    """
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    # Кука на этом устройстве тоже уже недействительна (token_version вырос) —
    # снимаем, чтобы не гонять заведомо мёртвый токен на /refresh неделю.
    _clear_refresh_cookie(response)
    logger.info("All sessions revoked: %s (%s)", mask_email(user.email), user.id)
    return MessageResponse(message="Вы вышли на всех устройствах.")
