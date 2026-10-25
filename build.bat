@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==============================================
echo   Gerando ReconhecimentoFacial.exe
echo ==============================================

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao encontrado.
    echo Instale o Python 3.12 em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" na instalacao.
    pause
    exit /b 1
)

if not exist venv (
    echo [1/4] Criando ambiente virtual...
    python -m venv venv || goto :erro
)
call venv\Scripts\activate.bat

echo [2/4] Instalando bibliotecas...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt || goto :erro

echo [3/4] Baixando modelos de reconhecimento facial...
if not exist models mkdir models
if not exist models\face_detection_yunet_2023mar.onnx (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -OutFile 'models\face_detection_yunet_2023mar.onnx'" || goto :erro
)
if not exist models\face_recognition_sface_2021dec.onnx (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx' -OutFile 'models\face_recognition_sface_2021dec.onnx'" || goto :erro
)

echo [4/4] Gerando o .exe (pode levar alguns minutos)...
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name ReconhecimentoFacial ^
    --add-data "models;models" ^
    --add-data "assets;assets" ^
    --icon "assets\icone.ico" ^
    reconhecimento.py || goto :erro

echo.
echo ==============================================
echo   PRONTO!  O programa esta em:
echo   %cd%\dist\ReconhecimentoFacial.exe
echo ==============================================
explorer dist
pause
exit /b 0

:erro
echo.
echo [ERRO] Algo deu errado. Copie a mensagem acima e envie para o suporte.
pause
exit /b 1
