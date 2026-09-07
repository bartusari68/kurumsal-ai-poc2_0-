@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
if not exist ".env" (
  echo .env dosyasi bulunamadi. .env.example dosyasini kopyalayip anahtarinizi ekleyin.
  goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-local.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\prepare_local_models.py --verify
if errorlevel 1 goto failed
echo Kurulum tamamlandi. baslat.cmd ile uygulamayi acabilirsiniz.
pause
exit /b 0
:failed
echo Kurulum tamamlanamadi. Yukaridaki hatayi kontrol edin. Mevcut PDF dosyalari korunur.
pause
exit /b 1
