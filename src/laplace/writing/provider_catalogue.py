"""THE PASSIVE PROVIDER CATALOGUE AND THE PROVIDER ERROR (standalone boundary, 2026-10-20): the dependency-neutral
owner of what the core reads about providers WITHOUT running one.

Owned here: ``ProviderError`` (the one exception class every provider boundary raises; ``writing_provider`` re-exports
the same object), the catalogue file under the checkout (``_catalogue_path``), the advertised-model spelling rules
(``advertised_model``, ``models_discovered``), the model-choice annotation (``with_model_choice``) and the PASSIVE read
``provider_catalogue``: the saved catalogue file, else the live discovery's memory when the adapter has already run
in this process (read through ``sys.modules``; never imported for it), else the installed-executable fallback rows.
Opening a view, reading a Work, starting a conversation or a child host consults this module; none of them imports
``laplace.writing.provider``, the one provider SERVICE (process spawn, streaming, interrupt, live ``capabilities``),
which stays the outward adapter and keeps its in-memory ``_CAP_CACHE`` (written by live discovery, read here when
present). One catalogue, one cache, one choice rule: moved, not duplicated.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
from pathlib import Path


class ProviderError(RuntimeError):
    pass


def _live_memory(root: Path) -> dict | None:
    """The live discovery's in-memory catalogue for ``root`` when the adapter already ran in this process; the adapter is
    looked up, never imported: a process that never discovered has no memory to read."""
    adapter = sys.modules.get('laplace.writing.provider')
    cache = getattr(adapter, '_CAP_CACHE', None) if adapter is not None else None
    return cache[1] if cache and getattr(adapter, '_CAP_CACHE_ROOT', None) == root else None


def _catalogue_path(cwd: Path) -> Path:
    return Path(cwd).resolve() / '.laplace-cache' / 'writing-provider-catalogue.json'


def advertised_model(provider_row: dict, token: str) -> dict | None:
    """The advertised catalogue row a model token names, in one deliberate order: an exact
    id or resolved id, then an id whose alias suffix is the only difference (``opus[1m]``
    for the deep tier's ``opus``), then a row whose RESOLVED id contains the token
    (``claude-sonnet-5``).

    The order is load-bearing.  The Claude catalogue's first row is the SDK's own unnamed
    `default` entry (:func:`_claude_models`, the ``value=='default'`` row), whose
    resolved_model is ``claude-opus-5[1m]`` -- so a resolved-token-first search would have
    answered the deep tier with the vendor's default row again, which is exactly the holder
    this lane removes.  The spellings come from ``schema.model_spellings``, the same
    mechanism ``schema.model_tier`` reads a row's tier with: one mechanism, both
    directions, and no alias list with a vendor's release schedule attached."""
    from laplace.pipeline import schema
    rows = provider_row.get('models') or []
    if not token:
        return None
    exact = next((row for row in rows if token in {row.get('id'), row.get('resolved_model')}), None)
    if exact is not None:
        return exact
    alias = next((row for row in rows if str(row.get('id') or '').split('[')[0] == token), None)
    if alias is not None:
        return alias
    spelled = next((row for row in rows
                    if token in schema.model_spellings('', row.get('resolved_model'))), None)
    if spelled is not None:
        return spelled
    # The alias suffix is the only difference in EITHER direction.  A pane that showed
    # ``claude-fable-5-1[1m]`` from an earlier catalogue still names the live row whose id
    # or resolved id is ``claude-fable-5-1``; refusing it as "not advertised" contradicts
    # the advertised dropdown the person chose from (ux/m5-live-pilot-friction.json).
    base = token.split('[')[0]
    if base and base != token:
        return advertised_model(provider_row, base)
    return None


def models_discovered(provider_row: dict) -> bool:
    """Whether this provider's models were really discovered.  A catalogue that failed
    discovery carries one placeholder row with an EMPTY id ('Configured model', the fallback
    built in :func:`provider_catalogue` and in :func:`capabilities`), which is no evidence
    about any model -- so a tier default resolves to the tier's own model name there instead
    of being refused against a list that does not exist."""
    return any(row.get('id') for row in (provider_row.get('models') or []))


def with_model_choice(catalogue: dict) -> dict:
    """Annotate a catalogue with model choice, DERIVED from the one tier table at read time.

    Every model row gains ``tier`` (``schema.model_tier``; null for a model the table does
    not name) and the one row per provider that IS this installation's session default gains
    ``session_default``; the catalogue gains the whole declaration under ``model_choice``
    (``schema.model_choice_declaration``).  Nothing here is stored: :func:`capabilities`
    banks the UNANNOTATED value in ``_CAP_CACHE`` and under :func:`_catalogue_path` and
    annotates on the way out, so a catalogue written before a tier moved cannot serve a
    stale tier, and the composer's pane has one field to read instead of a table of its own
    (``src/laplace/web/static_shared/workspace-session.mjs`` used the vendor's ``default``
    flag)."""
    from laplace.pipeline import schema
    declaration = schema.model_choice_declaration()
    session_models = declaration['role_defaults']['session']['models']
    providers = []
    for provider in catalogue.get('providers') or []:
        ident = str(provider.get('id') or '')
        wanted = session_models.get(ident)
        chosen = advertised_model(provider, wanted) if wanted else None
        models = []
        for row in provider.get('models') or []:
            value = {**row, 'tier': schema.model_tier(str(row.get('id') or ''), ident,
                                                      row.get('resolved_model'))}
            if chosen is not None and row is chosen:
                value['session_default'] = True
            models.append(value)
        providers.append({**provider, 'models': models})
    return {**catalogue, 'providers': providers, 'model_choice': declaration}


def _observation(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _provider_observation(row, catalogue):
    return _observation(row.get('observed_at', catalogue.get('observed_at')))


def _model_observation(row, catalogue):
    if 'model_observed_at' in row:
        return _observation(row['model_observed_at'])
    if row.get('model_catalogue_source') in {'last-known-good', 'installed-cache'} or not models_discovered(row):
        return None
    return _provider_observation(row, catalogue)


def reconcile_catalogues(saved: dict, memory: dict) -> dict:
    """One provider-qualified join for passive reads and the discovery writer's late merge.

    An attempt's state and its retained model catalogue have independent observation
    times. A newer Codex snapshot cannot select an older Claude row by proxy.
    """
    rank = lambda value: float('-inf') if value is None else value
    snapshots = (saved, memory)
    updated = lambda value: rank(_observation(value.get('updated_at', value.get('observed_at'))))
    result = dict(max(snapshots, key=updated))
    full = max(snapshots, key=lambda value: rank(_observation(value.get('observed_at'))))
    result['observed_at'] = full.get('observed_at')
    candidates = {}
    for snapshot in snapshots:
        for row in snapshot.get('providers') or []:
            candidates.setdefault(row['id'], []).append((row, snapshot))
    providers = []
    for choices in candidates.values():
        row, source = max(choices, key=lambda item: (rank(_provider_observation(*item)), updated(item[1])))
        selected = json.loads(json.dumps(row))
        if 'observed_at' not in selected and source.get('observed_at') != result.get('observed_at'):
            selected['observed_at'] = _provider_observation(row, source)
        model_row, model_source = max(choices, key=lambda item: rank(_model_observation(*item)))
        model_time = _model_observation(model_row, model_source)
        current_model_time = _model_observation(row, source)
        retained = (selected.get('model_catalogue_source') == 'last-known-good' or selected.get('error')
                    or selected.get('model_discovery_error') or not selected.get('available') or not models_discovered(selected))
        if retained and model_time is not None and (current_model_time is None or model_time > current_model_time):
            selected.update(models=json.loads(json.dumps(model_row['models'])), model_observed_at=model_time,
                            model_catalogue_source='last-known-good')
        providers.append(selected)
    result['providers'] = providers
    return result


def provider_catalogue(cwd: Path) -> dict:
    """Passive UI discovery. Opening a view never starts a provider process."""
    root = Path(cwd).resolve()
    memory = _live_memory(root)
    try:
        saved = json.loads(_catalogue_path(root).read_text(encoding='utf-8'))
        if saved.get('schema_version') == 'laplace.provider-catalogue/1' and isinstance(saved.get('providers'), list):
            value = saved if memory is None else reconcile_catalogues(saved, memory)
            return with_model_choice({**value, 'cached': True})
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if memory is not None:
        return with_model_choice({**memory, 'cached': True})
    providers = []
    for ident, name in [('codex', 'Codex'), ('claude', 'Claude')]:
        installed = bool(shutil.which(ident))
        providers.append({'id': ident, 'name': name, 'available': installed,
            'executable': installed, 'auth_state': 'UNVERIFIED', 'stream': True,
            'resume': True, 'steer': ident == 'codex', 'interrupt': True,
            'models': [{'id': '', 'name': 'Configured model', 'default': True,
                        'efforts': ['low', 'medium', 'high']}], 'custom_model': True})
    # Codex already keeps the account's model list locally. Reading it does not
    # start an App Server, an authentication probe, or an inference turn.
    try:
        home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
        cached_models = json.loads((home / 'models_cache.json').read_text(encoding='utf-8'))
        choices = [{'id': m['slug'], 'name': m.get('display_name') or m['slug'],
                    'description': m.get('description') or '',
                    'default': index == 0, 'default_effort': m.get('default_reasoning_level') or 'medium',
                    'efforts': [level['effort'] for level in m.get('supported_reasoning_levels', []) if level.get('effort')],
                    'context_window_advertised': m.get('max_context_window') or m.get('context_window')}
                   for index, m in enumerate(cached_models.get('models') or [])
                   if isinstance(m, dict) and m.get('slug') and m.get('visibility') == 'list']
        if choices:
            choices[0]['default'] = True
            providers[0]['models'] = choices
            providers[0]['model_catalogue_source'] = 'installed-cache'
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return with_model_choice({'schema_version': 'laplace.provider-catalogue/1', 'providers': providers,
            'cached': False, 'observed_at': None,
            'note': 'Provider availability is checked when sending a message or refreshing providers.'})
