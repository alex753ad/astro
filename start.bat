@echo off
title Astro SPA — Запуск
cd /d C:\Users\User\Desktop\astro

echo.
echo  ================================
echo   ASTRO SPA — Запуск приложения
echo  ================================
echo.

:: 1. Запуск базы данных
echo [1/3] Запускаю базу данных...
docker compose up -d db
if %errorlevel% neq 0 (
    echo ОШИБКА: Docker не запущен. Запустите Docker Desktop и попробуйте снова.
    pause
    exit /b 1
)
echo       База данных запущена.
echo.

:: 2. Ждём пока база поднимется
timeout /t 4 /nobreak >nul

:: 3. Запуск бэкенда в отдельном окне
echo [2/3] Запускаю бэкенд...
start "Astro Backend" cmd /k "cd /d C:\Users\User\Desktop\astro && .venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
echo       Бэкенд запускается...
echo.

:: 4. Ждём пока бэкенд поднимется
timeout /t 8 /nobreak >nul

:: 5. Запуск фронтенда в отдельном окне
echo [3/3] Запускаю фронтенд...
start "Astro Frontend" cmd /k "cd /d C:\Users\User\Desktop\astro\frontend && npm run dev"
echo       Фронтенд запускается...
echo.

:: 6. Ждём пока Vite поднимется и прокси настроится
timeout /t 12 /nobreak >nul

:: 7. Открываем браузер
echo  Открываю браузер...
start http://localhost:5173

echo.
echo  ================================
echo   Приложение запущено!
echo.
echo   Сайт:    http://localhost:5173
echo   API:     http://localhost:8000
echo   Docs:    http://localhost:8000/docs
echo  ================================
echo.
echo  Для остановки закройте окна "Astro Backend"
echo  и "Astro Frontend", затем выполните:
echo  docker compose stop
echo.
pause
