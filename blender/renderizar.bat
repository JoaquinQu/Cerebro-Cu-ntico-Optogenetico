@echo off
REM Renderiza el video de Cerebro Cuántico Optogenético con Blender (Windows).
REM Uso:  blender\renderizar.bat [eevee|cycles] [borrador|media|alta] [NEURONA]
REM Ej.:  blender\renderizar.bat eevee borrador AVM
setlocal
set MOTOR=%1
if "%MOTOR%"=="" set MOTOR=eevee
set CALIDAD=%2
if "%CALIDAD%"=="" set CALIDAD=media
set FUENTE=%3
if "%FUENTE%"=="" set FUENTE=AVM

REM Buscar blender.exe (variable BLENDER, PATH o instalación estándar)
if not defined BLENDER (
  where blender >nul 2>nul && set BLENDER=blender
)
if not defined BLENDER (
  for /d %%D in ("C:\Program Files\Blender Foundation\Blender*") do set BLENDER=%%D\blender.exe
)
if not defined BLENDER (
  echo No encontre Blender. Instalalo o define la ruta:  set BLENDER=C:\ruta\a\blender.exe
  exit /b 1
)

cd /d "%~dp0.."
python backend\scripts\exportar_blender.py --fuente %FUENTE% || exit /b 1
"%BLENDER%" --background --python blender\animar_gusano.py -- --render --motor %MOTOR% --calidad %CALIDAD%
echo.
echo Video en blender\render\
endlocal
