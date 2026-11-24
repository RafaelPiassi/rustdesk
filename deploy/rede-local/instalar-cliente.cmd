@echo off
rem Instala o Boa Safra Acesso Remoto a partir desta pasta.
rem Uso (como administrador):  instalar-cliente.cmd [SERIAL]
rem Com o serial, a licença já é ativada ao final.
setlocal
net session >nul 2>&1 || (echo Execute como administrador: clique com o botao direito ^> Executar como administrador. & pause & exit /b 1)

set "MSI="
for %%f in ("%~dp0*x86_64.msi") do set "MSI=%%f"
if not defined MSI (echo Nenhum instalador .msi encontrado em %~dp0 & pause & exit /b 1)

echo Instalando %MSI% ...
msiexec /i "%MSI%" /qb /norestart
if errorlevel 1 (echo A instalacao falhou ^(codigo %errorlevel%^). & pause & exit /b 1)

if "%~1"=="" goto fim
echo Ativando a licenca %~1 ...
timeout /t 10 /nobreak >nul
set "APP=%ProgramFiles%\BoaSafra\boasafra.exe"
if not exist "%APP%" (echo Nao encontrei %APP%; ative pela tela do programa. & goto fim)
"%APP%" --activate-license %~1

:fim
echo Pronto.
pause
