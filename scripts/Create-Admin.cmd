@echo off
setlocal
title I-Stay permanent administrator setup
cd /d "%~dp0.."
set "ISTAY_DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not exist "%ISTAY_DOCKER%" set "ISTAY_DOCKER=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
if not exist "%ISTAY_DOCKER%" exit /b 3
echo Create your permanent administrator. Use username admin.
echo Password input is hidden. Choose at least 14 characters and confirm privately.
echo Do not send the password in chat. This window does not record a transcript.
"%ISTAY_DOCKER%" compose --project-name istay-prod --env-file .env.local-staging -f compose.prod.yml -f compose.local-staging.yml exec api python -m app.cli create-admin
exit /b %errorlevel%
