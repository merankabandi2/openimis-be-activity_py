# openIMIS Backend Activity Module

This module provides PTBA (Plan de Travail et Budget Annuel) management for the openIMIS platform.

## Features

- PTBA hierarchy: Composante, SousComposante, Activite, SousActivite
- Activity lifecycle management (Planifie, Budgetise, En Cours, Realise, Cloture)
- Multi-donor funding source tracking
- Quarterly execution reporting
- Excel import from standard 44-column PTBA format

## Rights

| Code | Perm (module config) |
|------|----------------------|
| 802014-802017 | PTBA search, create, update, delete (`gql_ptba_*_perms`) |
| 802005-802008 | Activity search, create, update, delete |
| 802009 / 802010 | Execution report / approve |
| 802011 | Activity lifecycle transition |
| 802012 | Dashboard view |
| 802013 | Funding management |

170001-170004 are the social_protection beneficiary rights and give no PTBA
access. The `grant_ptba_rights` command of the merankabandi module gives
every live role holding 170001-170004 the matching PTBA right (170001 gives
802014, 170002 gives 802015, 170003 gives 802016, 170004 gives 802017). It
only adds rights and purges the rights cache of the users of changed roles:

```bash
python manage.py grant_ptba_rights           # dry run: prints the plan per role
python manage.py grant_ptba_rights --apply
```
