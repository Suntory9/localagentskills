# Doc Skill

Use this reference when the user is asking for internal office, IT, VPN, SSO, device, permission, onboarding, offboarding, or other company documentation through `xdoa doc`.

## Default goal

Prioritize fast, correct answers.

For common factual lookups, prefer:

- run 1 focused query using the user's wording
- inspect the top results
- open only the most relevant current, non-deprecated document
- answer immediately from the opened document

Do not expand into multiple query variants unless the first query is weak, ambiguous, deprecated, or returns no clearly relevant current document.

## Workflow

1. Search first:

```bash
rtk xdoa doc query "<keyword>" --json
```

2. Inspect the search results before opening documents:

- judge relevance from `title_path` and `preview`
- skip any result whose title path, preview, URL, or tags suggest it is deprecated, especially content containing `已废弃`
- prefer current, specific documents over broad or weakly related results
- if no useful non-deprecated result exists, say that the knowledge-base search did not find a reliable current document

3. Read the selected document:

```bash
rtk xdoa doc view "<doc_url_or_path>"
```

Use the `url` field returned by `doc query`; it may be a `/docs/...` path or a full URL.

4. Answer from the full document content:

- give the practical action path first
- mention caveats only when they matter
- if documents conflict, prefer the non-deprecated and more current-looking one and state uncertainty briefly

## Query guidance

- use the user's wording as the first query
- if results are weak, retry with 1-2 focused variants, such as product name, system name, error keyword, or Chinese/English synonyms
- do not answer from search snippets alone when a relevant document can be opened
- do not expose raw JSON unless the user asks for it
