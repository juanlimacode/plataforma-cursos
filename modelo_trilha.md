---
id: meu-novo-curso
versao: 1
titulo: "Nome do Curso"
descricao: "Descrição objetiva do curso que aparecerá no dashboard."
categoria: "Dados e Automação"
fonte: "Microsoft Learn"
xp_modo: "distribuir_xp_modulo_por_unidades"
xp_nivel_intervalo: 600
---

# Nome do Curso

> Modelo reutilizável para importação de novos cursos na plataforma.
> Mantenha os campos `id` estáveis e únicos para preservar o progresso dos alunos em futuras atualizações.

---

## Trilha: Trilha 1: Fundamentos
- id: trilha-1
- descricao: Resumo do que será visto nesta seção interna do curso.

### Módulo: Primeiro Módulo
- id: mod-1
- link: https://learn.microsoft.com/pt-br/training/
- etiqueta: Iniciante • 30 min
- xp: 300
- descricao: Descrição curta do módulo.

#### Unidade: Introdução
- id: u-1-1
- duracao: 10 min

#### Unidade: Conceitos principais
- id: u-1-2
- duracao: 15 min

#### Unidade: Resumo
- id: u-1-3
- duracao: 5 min

---

## Conquistas

### Conquista: Primeiro Passo
- id: ach-1
- descricao: Complete sua primeira unidade neste curso.
- icone: fa-solid fa-seedling
- tipo: unidades_concluidas
- operador: ">="
- meta: 1

### Conquista: Mestre do Curso
- id: ach-2
- descricao: Conclua 100% do curso.
- icone: fa-solid fa-crown
- tipo: percentual_conclusao
- operador: ">="
- meta: 100
