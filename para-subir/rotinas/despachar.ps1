# Publica no Instagram e no TikTok os vídeos cujo horário já chegou (as APIs deles não agendam).
# Agendar no Agendador de Tarefas do Windows para rodar a cada 5 minutos:
#   schtasks /Create /TN "Maquina de Videos - despachar" /SC MINUTE /MO 5 /TR "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File \"<pasta do projeto>\rotinas\despachar.ps1\""
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

python mv.py despachar
