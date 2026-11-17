# Plataforma Gamificada de Cursos

Evolução da trilha **Power BI & Power Platform** para uma plataforma multiusuário com autenticação, painel administrativo, importação de cursos via Markdown (`.md`) e persistência em SQLite.

## Estrutura

- `app.py`: servidor Flask, rotas de autenticação, cursos, progresso e administração.
- `db.py`: esquema SQLite (`users`, `courses`, `course_access`, `user_progress`) e seed inicial.
- `auth.py`: sessões HttpOnly e controle de permissões (`admin` / `user`).
- `md_importer.py`: parser e validador de cursos em Markdown.
- `progress.py`: cálculo de XP, níveis (600 XP), conclusão de módulos e conquistas reversíveis.
- `static/index.html` e `static/app.js`: interface responsiva preservando o design original.
- `modelo_trilha.md`: modelo reutilizável para importar novos cursos.
- `seed_power_bi.md`: definição inicial do curso **Power BI & Power Platform**.

## Como executar

```powershell
cd plataforma-cursos
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Acesse no navegador: `http://127.0.0.1:5000`

### Credenciais iniciais (desenvolvimento)

- **Usuário:** `ADMIN`
- **Senha:** `adminppnj`

## Testes

```powershell
.\.venv\Scripts\pytest.exe -v tests/test_platform.py
```
