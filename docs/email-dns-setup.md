# Email DNS Setup — aristeatime.ru

Настройка SPF, DKIM, DMARC для домена через Resend.

---

## 1. SPF

Добавь TXT-запись на `aristeatime.ru`:

| Тип | Хост | Значение |
|-----|------|----------|
| TXT | `@` | `v=spf1 include:amazonses.com ~all` |

> Resend отправляет через Amazon SES — включаем их диапазон.

---

## 2. DKIM

В панели Resend: **Domains → Add Domain → aristeatime.ru**  
Resend выдаст 2–3 CNAME-записи вида:

| Тип | Хост | Значение |
|-----|------|----------|
| CNAME | `resend._domainkey` | `resend._domainkey.amazonses.com` |

Добавь все CNAME-записи, которые показывает Resend, и нажми **Verify**.

---

## 3. DMARC

Добавь TXT-запись на `_dmarc.aristeatime.ru`:

| Тип | Хост | Значение |
|-----|------|----------|
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@aristeatime.ru; ruf=mailto:dmarc@aristeatime.ru; fo=1` |

Параметры:
- `p=quarantine` — подозрительные письма уходят в спам (не удаляются)
- `rua` — агрегированные отчёты (раз в сутки)
- `ruf` — форензик-отчёты по отдельным сбоям
- После 2–4 недель без проблем меняй на `p=reject`

---

## 4. Return-Path (опционально, +5 к репутации)

| Тип | Хост | Значение |
|-----|------|----------|
| CNAME | `bounce` | `feedback-smtp.eu-west-1.amazonses.com` |

В `.env`:
```
FROM_EMAIL=noreply@aristeatime.ru
```

---

## 5. Проверка

```bash
# SPF
dig TXT aristeatime.ru

# DKIM
dig CNAME resend._domainkey.aristeatime.ru

# DMARC
dig TXT _dmarc.aristeatime.ru
```

Онлайн-проверка: https://mxtoolbox.com/SuperTool.aspx

---

## 6. Checklist

- [ ] SPF TXT добавлен
- [ ] DKIM CNAME(s) добавлены и Resend показывает "Verified"
- [ ] DMARC TXT добавлен
- [ ] `FROM_EMAIL=noreply@aristeatime.ru` в `.env` на проде
- [ ] `RESEND_API_KEY` в переменных Railway/Vercel
- [ ] Через 48ч: проверить отчёты на `dmarc@aristeatime.ru`
- [ ] Через 2–4 нед: переключить DMARC `p=reject`
