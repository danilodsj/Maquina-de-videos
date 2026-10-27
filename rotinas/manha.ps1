# Rotina da manhã: garimpo, transcrição, triagem pelo Claude e pauta do dia.
# Agendar no Agendador de Tarefas do Windows:
#   powershell -ExecutionPolicy Bypass -File "<pasta do projeto>\rotinas\manha.ps1"
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

python mv.py garimpar
python mv.py transcrever
claude -p "Use a skill triagem para triar todos os pendentes e gerar a pauta de hoje. Depois atualize o painel online como descrito no CLAUDE.md (seção Painel online)." `
  --allowedTools "Read,Write,Bash(python mv.py:*),Artifact,ArtifactData"
