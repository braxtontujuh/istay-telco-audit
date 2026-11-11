@echo off
setlocal
cd /d "%~dp0.."
if not exist ".deployment.json" exit /b 2
findstr /c:"LocalStaging" ".deployment.json" >nul || exit /b 2
set "ISTAY_DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not exist "%ISTAY_DOCKER%" set "ISTAY_DOCKER=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
if not exist "%ISTAY_DOCKER%" exit /b 3
"%ISTAY_DOCKER%" info >nul 2>&1
if not errorlevel 1 goto start_services
set "ISTAY_DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not exist "%ISTAY_DESKTOP%" set "ISTAY_DESKTOP=C:\Program Files\Docker\Docker\Docker Desktop.exe"
if not exist "%ISTAY_DESKTOP%" exit /b 3
start "" /b "%ISTAY_DESKTOP%"
for /l %%N in (1,1,60) do (
  "%ISTAY_DOCKER%" info >nul 2>&1
  if not errorlevel 1 goto start_services
  timeout /t 10 /nobreak >nul
)
exit /b 4
:start_services
if not exist "logs" mkdir "logs"
"%ISTAY_DOCKER%" compose --project-name istay-prod --env-file .env.local-staging -f compose.prod.yml -f compose.local-staging.yml up -d --no-build >"logs\local-startup-last.log" 2>&1
exit /b %errorlevel%
