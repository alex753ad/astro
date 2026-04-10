@echo off
title Astro SPA — Остановка
cd /d C:\Users\User\Desktop\astro

echo.
echo  ================================
echo   ASTRO SPA — Остановка
echo  ================================
echo.

echo Останавливаю базу данных...
docker compose stop
echo Готово.
echo.
echo Закройте окна "Astro Backend" и "Astro Frontend" вручную.
echo.
pause
