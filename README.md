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
| 170014-170017 | PTBA search, create, update, delete (`gql_ptba_*_perms`) |
| 170005-170008 | Activity search, create, update, delete |
| 170009 / 170010 | Execution report / approve |
| 170011 | Activity lifecycle transition |
| 170012 | Dashboard view |
| 170013 | Funding management |

170001-170004 are the social_protection beneficiary rights and give no PTBA
access. `grant_ptba_rights` gives the PTBA rights to the roles that hold
170001-170004 together with at least one activity right (170001 gives
170014, 170002 gives 170015, 170003 gives 170016, 170004 gives 170017). It
only adds rights and purges the rights cache of the users of changed roles:

```bash
python manage.py grant_ptba_rights           # dry run: prints the plan per role
python manage.py grant_ptba_rights --apply
```
