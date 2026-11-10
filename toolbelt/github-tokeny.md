# Tożsamość i tokeny GitHub per agent

Lekcja z praktyki: jedno konto `gh` dla całej floty = brak rozliczalności (nie wiadomo, który agent scalił, kto wypchnął).
W szablonie każdy agent ma własną tożsamość GitHub o minimalnym zakresie, a hook uprawnień ogranicza, co z nią zrobi.

## Wariant zalecany: GitHub App organizacji
1. **[operator]** W organizacji GitHub: Settings → Developer settings → GitHub Apps → New. Uprawnienia repo:
   Contents (read/write), Pull requests (read/write), Issues (read/write), Metadata (read). Bez uprawnień do
   Administration, Secrets, Actions. Zainstaluj w repo organizacji i repo produktu.
2. **[operator]** Klucz prywatny App → menedżer sekretów (`op://agenci/github-app/private-key`), App ID i Installation ID
   w `toolbelt/env/wspolne.env`.
3. Agent na starcie przebiegu dostaje krótkotrwały token instalacyjny (1 h) z `scripts/gh-token.sh <rola>`
   (do napisania w etapie E: JWT z klucza App → `POST /app/installations/<id>/access_tokens`), ustawiony jako `GH_TOKEN`.
   Commity: `git -c user.name="<rola> (agent)" -c user.email="<rola>@<domena>"` – autor widoczny w historii.
4. Rozliczalność: `gh api` i commity podpisane nazwą roli; blokady hooka w `bezpieczenstwo/blokady.jsonl`.

## Wariant prosty (pierwsza firma): fine-grained PAT per rola
- **[operator]** Jeden PAT na rolę z dostępu do konta technicznego firmy (nie prywatnego!): `github-pat-ceo`,
  `github-pat-inzynier`, `github-pat-recenzent`… Zakres: tylko repo organizacji i produktu; recenzent i PM – Contents
  read, Pull requests read/write (werdykty), Issues read/write; inżynier i architekt – Contents read/write,
  Pull requests read/write; CEO – jak inżynier + merge (przez hook tylko z werdyktem).
- Ważność 90 dni, rotacja w kalendarzu agenta bezpieczeństwa.
- W przebiegu: `op run --env-file=toolbelt/env/<rola>.env -- <polecenie>` ustawia `GH_TOKEN`.

## Czego nie robić
- Nie używać prywatnego konta właściciela do pracy agentów.
- Nie dawać agentom uprawnień Administration ani Secrets (zmiany ustawień repo = poziom `zmiana_ustawien_uslugi`).
- Nie zapisywać tokenu w pliku repo, dzienniku ani raporcie (hook raportu i strażnik maskują `ghp_…`, `github_pat_…`).
