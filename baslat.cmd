@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
  echo Sanal ortam bulunamadi. Once README dosyasindaki kurulum adimlarini uygulayin.
  pause
  exit /b 1
)

echo Kurumsal AI POC baslatiliyor: http://127.0.0.1:8000
rem Tek islem: model bellegi ve indeksleme kilidi worker'lar arasinda paylasilmaz.
".venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
endlocal
