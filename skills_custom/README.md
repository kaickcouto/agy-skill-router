# Custom Skills (Regras Proprietárias & Módulos)

Coloque aqui as skills customizadas do seu negócio ou projeto (ex: regras de faturamento, comissões, arquitetura interna de microserviços).

## Como criar uma skill customizada:
1. Crie uma pasta com o nome da skill: `skills_custom/minha-regra-cms/`
2. Crie o arquivo `SKILL.md` dentro dela com o frontmatter padrão:

```markdown
---
name: minha-regra-cms
description: "Regras de negócio proprietárias para o módulo CMS da empresa."
---

# Regras do CMS
- Descreva aqui os padrões internos da sua empresa.
```

O roteador detecta e ativa essa pasta automaticamente com **prioridade máxima** sobre o vault público!
