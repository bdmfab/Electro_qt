@echo off
rem Build the Windows program: run from the project folder.  Needs Python 3.10+ (and Inno Setup 6 for the installer).
python -m venv build_venv || goto :err
call build_venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :err
pyinstaller --noconfirm --clean packaging\electro_qt.spec || goto :err
echo.
echo Program folder: dist\Electro_qt   (run dist\Electro_qt\Electro_qt.exe)
where iscc >nul 2>nul
if %errorlevel%==0 (
  for /f %%v in ('python -c "import electro;print(electro.__version__)"') do iscc /DAppVersion=%%v packaging\electro_qt.iss
  echo Installer: dist\Electro_qt_Setup.exe
) else (
  echo Inno Setup not found: zip dist\Electro_qt to hand it out, or install Inno Setup 6 and run again.
)
exit /b 0
:err
echo BUILD FAILED
exit /b 1
