---
name: Deploy workflow e build AtuDIC
description: Fluxo completo de entrega — commit + push + scp + build installer Windows
type: feedback
---

## Fluxo de Entrega (após cada bloco de edições)

1. `git add` nos arquivos alterados + `git commit` com mensagem Conventional Commits (em Português/pt-BR)
2. `git push origin main`
3. `scp` dos arquivos alterados para a VM Windows (mantendo estrutura de pastas)

**Acesso à VM:**
- User: `tiago@192.168.122.41`
- Chave SSH: `~/.ssh/id_rsa_aturpo` com `-o IdentitiesOnly=yes`
- Pasta destino: `C:\Users\tiago\workspace\aturpo_demo\`

**Comando SCP:**
```
scp -o IdentitiesOnly=yes -i ~/.ssh/id_rsa_aturpo <arquivo> 'tiago@192.168.122.41:C:/Users/tiago/workspace/aturpo_demo/<path>/'
```

**Why:** Controle de versão sincronizado com ambiente de teste na VM Windows.

**How to apply:** Após cada bloco de edições, sem que o usuário precise pedir.

---

## Build Installer Windows (`build_installer.py`)

### Como rodar (na VM Windows)
```
cd C:\Users\tiago\workspace\aturpo_demo
python build_installer.py
```

### Pipeline do build (6 etapas)
1. **Verificar requisitos** — PyArmor, PyInstaller, JS Obfuscator, Inno Setup
2. **Limpar builds anteriores** — remove aturpo_win/obfuscated/, build/, dist/, Output/
3. **Minificar frontend** — scripts/minify_assets.py (JS/CSS)
4. **Ofuscar Python** — PyArmor gen (run.py + app/ recursivo)
   - Fallback: copia sem ofuscação se PyArmor falhar
   - Copia extras: static/, prompt/skills/, prompt/*.yml, prompt/*.md,
     index.html, theme.css, license_system.py, activate_license.*,
     security_enhancements.py, app/database/knowledge_seed.json
5. **Ofuscar JavaScript** — javascript-obfuscator em 20 arquivos .js
   - Fallback: mantém original se falhar (build continua)
6. **Criar executável** — PyInstaller com .spec customizado → ATUDIC.exe
7. **Criar instalador** — Inno Setup (installer.iss) → ATUDIC_Setup_X.X.X.exe

### Saída
- `aturpo_win/dist/ATUDIC.exe` — executável standalone
- `aturpo_win/Output/ATUDIC_Setup_{VERSION}.exe` — instalador Windows

### Configurações no script
- `VERSION = "1.0.0"` — versão atual
- `APP_NAME = "AtuDIC"`
- `AUTHOR = "Barbito / Normatel"`
- `BUILD_DIR = aturpo_win/`

### Pré-requisitos na VM Windows
- Python 3.12+ com pip
- `pip install pyarmor pyinstaller psycopg2-binary flask flask-cors bcrypt requests psutil`
- `npm install -g javascript-obfuscator` (opcional)
- Inno Setup 6 instalado (para .exe instalador)

### Artefatos copiados para o build
| Arquivo/Pasta | Destino no build | Obrigatório |
|---------------|-----------------|-------------|
| run.py | raiz (ofuscado) | Sim |
| app/ | app/ (ofuscado) | Sim |
| static/ | app/static/ | Sim |
| prompt/skills/*.md | prompt/skills/ | Sim |
| prompt/ATUDIC_AGENT_CONTEXT*.md | prompt/ | Sim |
| prompt/specialists.yml | prompt/ | Sim |
| prompt/chains.yml | prompt/ | Sim |
| index.html, theme.css | raiz | Sim |
| license_system.py | raiz | Sim |
| activate_license.* | raiz | Sim |
| memory/MEMORY.md, TOOLS.md | memory/ | Sim |
| app/database/knowledge_seed.json | app/database/ | Sim |
| installer.iss | raiz (Inno Setup) | Para .exe |
| aturpo_win/nssm.exe | dist/ | Para serviço Windows |

### Ao adicionar novos arquivos ao projeto, verificar:
1. Se é .py em app/ → já é pego automaticamente pelo PyArmor + hiddenimports
2. Se é .js em static/js/ → adicionar na lista `js_files` do `obfuscate_javascript()`
3. Se é .md em prompt/skills/ → já é pego automaticamente pelo copytree
4. Se é arquivo na raiz (html, css, py) → adicionar em `root_files_to_copy`
5. Se é data file (json, yml) → adicionar em `data_files_to_copy` ou no spec `datas`

**Why:** Build gera o instalador Windows do AtuDIC. Precisa estar sincronizado com mudanças estruturais.

**How to apply:** Verificar build_installer.py sempre que adicionar novos módulos, arquivos JS, skills ou dados.
