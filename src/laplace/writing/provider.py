"""On-demand provider connections for the scanner's continuing writing sessions.

Providers own their native conversation history. Laplace owns project context,
author decisions and exact manuscript rewrite receipts. No provider process is
started at import or left running between turns.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from typing import Callable
from contextlib import nullcontext


# the exception class and the passive catalogue live at their dependency-neutral owner; the same objects are public here
from laplace.core import bodies as core_bodies
from laplace.writing.provider_catalogue import (ProviderError, _catalogue_path, advertised_model, models_discovered,  # noqa: F401
                                                with_model_choice, provider_catalogue)


EDIT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "edits": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"file": {"type": "string"},
                           "line_start": {"type": "integer"}, "line_end": {"type": "integer"},
                           "before": {"type": "string"}, "after": {"type": "string"},
                           "reason": {"type": "string"},
                           "develops": {"type": "array", "items": {"type": "object",
                               "additionalProperties": False, "properties": {"id": {"type": "string"},
                               "content_revision": {"type": "string"}}, "required": ["id", "content_revision"]}},
                           "evidence_refs": {"type": "array", "items": {"type": "object",
                               "additionalProperties": False, "properties": {"id": {"type": "string"},
                               "revision": {"type": "string"}}, "required": ["id", "revision"]}}},
            "required": ["file", "line_start", "line_end", "before", "after", "reason",
                         "develops", "evidence_refs"],
        }},
    }, "required": ["answer", "edits"],
}

# These are documented model limits for the currently supported Codex IDs.  An
# App Server token-usage notification supersedes this catalogue for a live turn.
_CODEX_CONTEXT_WINDOWS = {
    "gpt-6-astra": 1_050_000,
    "gpt-6.1-sol": 1_050_000,
    "gpt-6-luna": 1_050_000,
    "gpt-5.6-sol": 1_050_000,
    "gpt-5.6-terra": 1_050_000,
    "gpt-5.6-luna": 1_050_000,
}


def context_window_advertised(provider: str, model: str):
    """Documented model maximum; blank/unknown selections intentionally stay unknown."""
    if provider=='codex':return _CODEX_CONTEXT_WINDOWS.get(model)
    if provider=='claude' and _CAP_CACHE:
        for item in _CAP_CACHE[1].get('providers',[]):
            if item.get('id')!='claude':continue
            found=next((row for row in item.get('models',[]) if model in
                        {row.get('id'),row.get('resolved_model')}),None)
            if found:return found.get('context_window_advertised')
    return None


def context_window_max(provider: str, model: str, usage=None):
    """Effective window only when reported; a catalogue maximum stays separate telemetry."""
    if provider == "codex" and isinstance(usage, dict):
        reported = ((usage.get("thread_token_usage") or {}).get("modelContextWindow"))
        if isinstance(reported, int) and not isinstance(reported, bool):
            return reported
    if provider == "codex":
        return None
    if provider == "claude" and isinstance(usage, dict):
        models = usage.get("model_usage") or {}
        if model:
            direct = models.get(model)
            if isinstance(direct, dict) and isinstance(direct.get("contextWindow"), int):
                return direct["contextWindow"]
            stem = str(model).split("[", 1)[0]
            matches = [row for key, row in models.items()
                       if str(key).split("[", 1)[0] == stem and isinstance(row, dict)]
            if len(matches) == 1 and isinstance(matches[0].get("contextWindow"), int):
                return matches[0]["contextWindow"]
        elif len(models) == 1:
            row = next(iter(models.values()))
            if isinstance(row, dict) and isinstance(row.get("contextWindow"), int):
                return row["contextWindow"]
    return None


def usage_projection(provider: str, reported, context_window=None) -> dict | None:
    """Compatibility counts only; the accompanying usage_basis declares their scope."""
    from laplace.writing import operating as writing_operating
    if reported is None:return None
    raw=(reported or {}).get('last') or {} if provider=='codex' else reported or {}
    counts,_input=_usage_counts(provider,raw)
    return {'provider':provider,**counts,'context_window':context_window if context_window is not None
            else (reported or {}).get('modelContextWindow') if provider=='codex' else None}


def context_tokens_used(usage):
    """Complete disjoint input proxy; missing components are unknown, never zero."""
    parts=[(usage or {}).get(key) for key in ('input','cached_input','cache_write_input')]
    return sum(parts) if all(_count(value) is not None for value in parts) else None


def turn_output(policy: dict, values: dict) -> dict:
    """ONE turn result shape, built from the policy's declared key list on both transports.

    `required` keys are always present, null where this transport has no such thing (a CLI
    turn has no provider turn identity); an `optional` key is present only when it has a
    value.  Before this, each adapter assembled its own dictionary and `proposal`,
    `turn_id` and `resolved_model` were per-transport accidents of which branch ran.
    """
    spec = policy["turn_output"]
    declared = list(spec["required"]) + list(spec["optional"])
    unknown = sorted(set(values) - set(declared))
    if unknown:
        raise ProviderError("A turn result carried undeclared keys: " + ", ".join(unknown))
    out = {key: values.get(key) for key in spec["required"]}
    out.update({key: values[key] for key in spec["optional"]
                if values.get(key) is not None})
    return out


def _codex_token_usage(value):
    """Project the installed App Server ThreadTokenUsage notification shape."""
    if not isinstance(value, dict):
        return None
    keys = ("cachedInputTokens", "cacheWriteInputTokens", "inputTokens", "outputTokens",
            "reasoningOutputTokens", "totalTokens")
    def breakdown(row):
        if not isinstance(row, dict):
            return None
        return {key: row[key] for key in keys if isinstance(row.get(key), int)
                and not isinstance(row.get(key), bool)}
    last, total = breakdown(value.get("last")), breakdown(value.get("total"))
    if last is None or total is None:
        return None
    result = {"last": last, "total": total}
    if isinstance(value.get("modelContextWindow"), int) and not isinstance(value.get("modelContextWindow"), bool):
        result["modelContextWindow"] = value["modelContextWindow"]
    return result


def _claude_assistant_usage(value):
    """One stream-json assistant message's actual usage, never the result aggregate."""
    return dict(value) if isinstance(value, dict) else None




def _claude_model_usage(result):
    value = result.get("modelUsage") if isinstance(result, dict) else None
    return dict(value) if isinstance(value, dict) else None


# These source contracts are additive; historical usage rows remain unchanged.
_USAGE_NATIVE_MAX_BYTES = 2 * 1024 * 1024
_USAGE_NATIVE_MAX_LINE = 64 * 1024


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage_counts(provider, raw):
    """Disjoint input components and output with its reasoning subset."""
    raw = raw if isinstance(raw, dict) else {}
    if provider == 'codex':
        def take(camel, snake):return _count(raw.get(camel, raw.get(snake)))
        incoming=take('inputTokens','input_tokens');cached=take('cachedInputTokens','cached_input_tokens')
        written=take('cacheWriteInputTokens','cache_write_input_tokens')
        output=take('outputTokens','output_tokens');reasoning=take('reasoningOutputTokens','reasoning_output_tokens')
        uncached=(incoming-cached-written if None not in (incoming,cached,written) and incoming>=cached+written else None)
        total=take('totalTokens','total_tokens')
    else:
        incoming=_count(raw.get('input_tokens',raw.get('inputTokens')))
        cached=_count(raw.get('cache_read_input_tokens',raw.get('cacheReadInputTokens')))
        written=_count(raw.get('cache_creation_input_tokens',raw.get('cacheCreationInputTokens')))
        uncached=incoming;output=_count(raw.get('output_tokens',raw.get('outputTokens')))
        reasoning=_count(raw.get('reasoning_output_tokens',raw.get('thinkingTokens')))
        if reasoning is None:
            details=raw.get('output_tokens_details')
            reasoning=_count(details.get('thinking_tokens')) if isinstance(details,dict) else None
        total=_count(raw.get('total_tokens',raw.get('totalTokens')))
        incoming=sum((uncached,cached,written)) if None not in (uncached,cached,written) else None
    if total is None and incoming is not None and output is not None:total=incoming+output
    return {'input':uncached,'cached_input':cached,'cache_write_input':written,
            'output':output,'reasoning_output':reasoning,'total':total},incoming


def usage_facts_projection(value):
    from laplace.writing.operating import usage_facts_projection as project
    return project(value)


def _counter_metadata(raw):
    """Whitelist typed metadata at every depth, with explicit omitted-byte coverage."""
    from laplace.writing import operating as wo
    from laplace.representation import writing_bodies as bodies
    import math
    def project(value):
        result={}
        for key,item in value.items():
            if key in wo.USAGE_RAW_COUNTS and (item is None or _count(item) is not None):result[key]=item
            elif key in wo.USAGE_RAW_COSTS and (item is None or isinstance(item,(int,float)) and not isinstance(item,bool) and math.isfinite(item) and item>=0):result[key]=item
            elif key in wo.USAGE_RAW_IDENTITIES and isinstance(item,str) and len(item.encode('utf-8'))<=256 and '\n' not in item:result[key]=item
            elif key in wo.USAGE_RAW_NESTED_COUNTS and isinstance(item,dict):
                result[key]={name:count for name,count in item.items() if name in wo.USAGE_RAW_NESTED_COUNTS[key] and (count is None or _count(count) is not None)}
            elif key=='iterations' and isinstance(item,list):result[key]=[project(row) for row in item if isinstance(row,dict)]
        return result
    filtered=project(raw if isinstance(raw,dict) else {})
    original=core_bodies.encode(raw);retained=core_bodies.encode(filtered)
    return filtered,{'state':'filtered_counter_metadata','original_bytes':len(original),'retained_bytes':len(retained),
        'omitted_bytes':max(0,len(original)-len(retained)),'full_provider_event_retained':False}


def _claude_init_customizations(value):
    """Reported visibility metadata, distinct from effective instruction contents."""
    from laplace.representation import writing_bodies as bodies
    import hashlib
    fields={}
    for key in ('output_style','skills','agents','slash_commands'):
        if key not in value:
            fields[key]={'state':'UNKNOWN','reason':'not reported by init'};continue
        item=value[key];raw=core_bodies.encode(item)
        shape='null' if item is None else 'array' if isinstance(item,list) else 'object' if isinstance(item,dict) else type(item).__name__
        fact={'state':'OBSERVED','shape':shape,'bytes':len(raw),'sha256':'sha256:'+hashlib.sha256(raw).hexdigest(),
              'effective_instruction_contents':'UNOBSERVABLE'}
        # Preserve the provider's actual scalar/list shape. Do not infer object schemas.
        safe=isinstance(item,str) or isinstance(item,list) and all(isinstance(row,str) for row in item)
        if safe and len(raw)<=8192:fact.update(value=item,omitted_bytes=0)
        else:fact.update(value=None,omitted_bytes=len(raw),reason='metadata value omitted: unsupported shape or byte bound')
        if isinstance(item,(list,dict)):fact['reported_count']=len(item)
        fields[key]=fact
    return {'source':'claude.system/init','fields':fields,'effective_customization_closure':'UNPROVEN'}


class _UsageFacts:
    def __init__(self,provider,root,logical_turn_id=None,admitted_model=None):
        from laplace.writing import operating as writing_operating
        self.version=writing_operating.USAGE_FACTS_VERSION
        self.provider=provider;self.root=Path(root);self.logical_turn_id=logical_turn_id
        self.attempt_id='PA-'+uuid.uuid4().hex;self.binding=None;self.turn=None;self.epoch=0
        self.observations=[];self.models=[];self.keys={};self.baseline={'kind':'unknown','coverage':'unknown'}
        self.native={'state':'unavailable','trace_coverage':'unknown'};self.cumulative=None;self.assistants={};self.started=time.monotonic()
        self.admitted_model=admitted_model

    def bind(self,binding,turn=None,*,fresh=False):
        from laplace.writing import operating as writing_operating
        if self.binding and binding!=self.binding:self.epoch+=1
        self.binding=binding
        if turn:self.turn=turn
        if fresh:self.baseline={'kind':'zero_fresh_binding','native_binding_id':binding,
            'reset_epoch':self.epoch,'value':{k:0 for k in writing_operating.USAGE_FACTS_CONTRACT['counts']},
            'coverage':'new thread/start without seeded history'}

    def model(self,name,source,*,actual=False):
        if not isinstance(name,str) or not name:return
        row={'admitted_model':self.admitted_model,'resolved_alias':name if not actual else None,
             'actual_reported_model':name if actual else None,'source':source}
        if row not in self.models:self.models.append(row)

    def observe(self,raw,scope,basis,phase='stream',*,domain='main_conversation',request_id=None,event_key=None,complete='complete_for_reported_scope'):
        from laplace.writing import operating as writing_operating
        from laplace.representation import writing_bodies as bodies
        contract=writing_operating.USAGE_FACTS_CONTRACT
        if scope not in contract['counter_scopes'] or phase not in contract['phases'] or domain not in contract['counter_domains']:
            raise ValueError('Undeclared usage observation vocabulary')
        filtered,raw_coverage=_counter_metadata(raw)
        encoded=core_bodies.encode(filtered)
        digest='sha256:'+__import__('hashlib').sha256(encoded).hexdigest()
        counts,context=_usage_counts(self.provider,filtered)
        key=(scope,basis,domain,request_id or event_key or digest,self.epoch,digest)
        if key in self.keys:
            item=self.keys[key]
            item['raw_metadata_coverage']=raw_coverage
            if phase=='terminal':item['phase']='terminal'
            if phase not in item['phases_observed']:item['phases_observed'].append(phase)
            return item
        try:
            handle=bodies.store(self.root).put(encoded);custody_error=None
        except Exception as error:
            handle=None;custody_error=str(error) # retain bounded filtered metadata inline
        if counts['reasoning_output'] is not None and counts['output'] is not None and counts['reasoning_output']>counts['output']:
            complete='inconsistent_reported_counts'
        if counts['total'] is not None and context is not None and counts['output'] is not None and counts['total']!=context+counts['output']:
            complete='inconsistent_reported_counts'
        item={'observation_id':'UO-'+uuid.uuid4().hex,'attempt_id':self.attempt_id,
              'logical_turn_id':self.logical_turn_id,'provider':self.provider,'native_binding_id':self.binding,
              'native_turn_id':self.turn,'provider_request_id':request_id,'source_event_key':event_key,
              'counter_scope':scope,'counter_domain':domain,'phase':phase,'phases_observed':[phase],
              'basis':basis,'reset_epoch':self.epoch,'raw_metadata_coverage':raw_coverage,'monotonic_offset_ms':(time.monotonic()-self.started)*1000,
              'counts':counts,'context_input_proxy':context,'inclusion':{'raw_input_includes_cache_read':self.provider=='codex',
              'raw_input_includes_cache_write':self.provider=='codex','reasoning_is_subset_of_output':True},
              'completeness':complete,'coverage':'only the stated provider counter domain; no invoice or unseen platform usage',
              'raw_observation_ref':{'schema_version':core_bodies.REFERENCE_SCHEMA,'content_handle':handle,
                  'store':'contract/writing_bodies','bytes':len(encoded),'encoding':'application/json'} if handle else None}
        if custody_error:item.update(raw_observation=filtered,raw_custody_error=custody_error)
        for cost_field in ('costUSD','total_cost_usd'):
            if cost_field in filtered:item['reported_cost_estimate']={'value':filtered[cost_field],'source_field':cost_field,'cost_basis':filtered.get('costBasis'),'source':basis,'counter_domain':domain,'invoice':False}
        self.observations.append(item);self.keys[key]=item
        return item

    def codex(self,value,phase='stream'):
        if not isinstance(value,dict):return
        total=value.get('total') or {};amount=_count(total.get('totalTokens'))
        if self.cumulative is not None and amount is not None and amount<self.cumulative:
            self.epoch+=1;self.baseline={'kind':'unknown','reason':'reported cumulative counter decreased','coverage':'reset gap'}
        if amount is not None:self.cumulative=amount
        event='appserver-'+__import__('hashlib').sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        if isinstance(value.get('last'),dict):self.observe(value['last'],'last_request','codex.appserver.last',phase,event_key=event)
        if isinstance(value.get('total'),dict):self.observe(value['total'],'binding_cumulative','codex.appserver.total',phase,domain='provider_all',event_key=event)

    def claude_assistant(self,message):
        ident=message.get('id');raw=message.get('usage')
        if not isinstance(raw,dict):return
        item=self.observe(raw,'last_request','claude.assistant.usage',request_id=ident,
            complete='complete_for_reported_scope' if ident else 'partial')
        if ident:self.assistants[ident]=item
        self.model(message.get('model'),'assistant_model',actual=True)

    def claude_terminal(self,result):
        raw=result.get('usage')
        if isinstance(raw,dict):self.observe(raw,'logical_turn','claude.result.usage','terminal',
            complete='complete_for_reported_scope' if _count(raw.get('output_tokens')) is not None else 'partial')
        process_metrics={key:result[key] for key in ('total_cost_usd','duration_ms','duration_api_ms','num_turns') if key in result}
        if process_metrics:self.observe(process_metrics,'unknown','claude.result.process_metrics','terminal',domain='unknown',complete='scope_unknown')
        for model,usage in (result.get('modelUsage') or {}).items():
            if isinstance(usage,dict):self.observe(usage,'unknown','claude.result.modelUsage','terminal',domain='unknown',
                request_id=model,complete='scope_unknown')

    def native_codex(self,path,start,stamp):
        """Only an admitted native path and bounded current-turn counter tail."""
        if not path or not self.binding or not self.turn or start is None or stamp is None:
            self.native={'state':'unavailable','trace_coverage':'unknown','reason':'no admitted native file identity/bytecut'};return
        candidate=Path(path)
        if not candidate.is_absolute() or self.binding not in candidate.name or candidate.is_symlink():
            self.native={'state':'unavailable','reason':'owned thread path identity is not proven'};return
        try:
            stat=candidate.stat()
            if stamp and (stat.st_dev,stat.st_ino)!=stamp:raise ValueError('native file identity changed')
            end=stat.st_size;begin=max(start or 0,end-_USAGE_NATIVE_MAX_BYTES)
            self.native={'state':'observed_bytecut','start':begin,'end':end,'admission_start':start,
                         'omitted_before':max(0,begin-(start or 0)),
                         'trace_coverage':'partial' if begin>(start or 0) else 'complete_bytecut',
                         'skipped_oversize_lines':0,'direct_counter_basis':'exact admitted path/thread/turn; independent of trace prefix'}
            with candidate.open('rb') as stream:
                stream.seek(begin)
                if begin>(start or 0):stream.readline(_USAGE_NATIVE_MAX_LINE)
                while stream.tell()<end:
                    line=stream.readline(min(_USAGE_NATIVE_MAX_LINE,end-stream.tell()))
                    if not line:break
                    if not line.endswith(b'\n'):
                        self.native['skipped_oversize_lines']+=1
                        self.native['trace_coverage']='partial'
                        while stream.tell()<end and line and not line.endswith(b'\n'):
                            line=stream.readline(min(_USAGE_NATIVE_MAX_LINE,end-stream.tell()))
                        continue
                    marker=re.search(br'"type"\s*:\s*"([^"\\]+)"',line[:256])
                    if marker is None or marker.group(1)!=b'token_usage_record':continue
                    try:row=json.loads(line)
                    except ValueError:continue
                    value=row.get('payload') or {}
                    if row.get('type')!='token_usage_record' or value.get('thread_id')!=self.binding or value.get('turn_id')!=self.turn:continue
                    request=value.get('response_id')
                    for field,scope,domain in [('usage','last_request','main_conversation'),('turn_token_usage','logical_turn','main_conversation'),('thread_token_usage','binding_cumulative','provider_all')]:
                        if isinstance(value.get(field),dict):self.observe(value[field],scope,'codex.native.'+field,'terminal',domain=domain,request_id=request)
        except (OSError,ValueError) as error:self.native={'state':'unavailable','reason':str(error)}

    @staticmethod
    def _selection(item):
        value= {'observation_id':item['observation_id'],'basis':item['basis'],'counter_scope':item['counter_scope'],
                'counter_domain':item['counter_domain'],'counts':item['counts'],'completeness':item['completeness'],
                'raw_observation_ref':item['raw_observation_ref']}
        if item.get('reported_cost_estimate') is not None:value['reported_cost_estimate']=item['reported_cost_estimate']
        return value

    def snapshot(self):
        from laplace.writing import operating as wo
        rows=[r for r in self.observations if r['reset_epoch']==self.epoch]
        request=next((r for r in reversed(rows) if r['counter_scope']=='last_request'),None)
        logical=next((r for r in reversed(rows) if r['counter_scope']=='logical_turn' and r['completeness']=='complete_for_reported_scope'),None)
        cumulative=next((r for r in reversed(rows) if r['counter_scope']=='binding_cumulative'),None)
        selected={'context_snapshot':None,'logical_turn':None,'binding_cumulative':None,'unselected_variants':[]}
        if request:
            selected['context_snapshot']={**self._selection(request),'counter_scope':'context_snapshot',
                'value':request['context_input_proxy'],'metric':wo.USAGE_CONTEXT_PROXY_METRIC,'exact_post_compaction_occupancy':'UNOBSERVABLE'}
        if logical:selected['logical_turn']=self._selection(logical)
        elif self.provider=='codex' and cumulative and cumulative['completeness']=='complete_for_reported_scope' and self.baseline.get('kind')=='zero_fresh_binding' and self.baseline.get('reset_epoch')==self.epoch:
            selected['logical_turn']={**self._selection(cumulative),'counter_scope':'logical_turn',
                'basis':wo.USAGE_FRESH_BINDING_BASIS,'derivation':'new thread/start zero baseline; no prior turns',
                'baseline':self.baseline}
        if cumulative:selected['binding_cumulative']=self._selection(cumulative)
        selected['unselected_variants']=[self._selection(r) for r in rows if r['counter_scope']=='unknown']
        return {'schema_version':self.version,'attempt_id':self.attempt_id,'logical_turn_id':self.logical_turn_id,
            'provider':self.provider,'native_binding_id':self.binding,'native_turn_id':self.turn,'reset_epoch':self.epoch,
            'observations':self.observations,'selected':selected,'baseline':self.baseline,
            'model_observations':self.models,'coverage':{'native_metadata':self.native,
                'logical_turn_total':'observed' if logical else 'derived_fresh_binding' if selected['logical_turn'] else 'unknown',
                'legacy_rows':'unchanged; no retrospective basis assignment','missing_scope':'unknown, never zero'}}



class ProcessRegistrationError(ProviderError):
    """The trusted spawn observer refused ownership before provider traffic."""


def _publish_spawn(process, on_spawn, phase: str, *, cleanup_grace=3):
    if on_spawn is None:return
    try:
        on_spawn(process, phase)
    except Exception as exc:
        # This Popen handle is ours, before initialization or prompt submission.
        try:
            import psutil
            owned = psutil.Process(process.pid)
            descendants = owned.children(recursive=True)
            for child in reversed(descendants):
                try:child.terminate()
                except psutil.Error:pass
            process.terminate()
            try:process.wait(timeout=cleanup_grace)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=3)
            _, alive = psutil.wait_procs(descendants, timeout=1)
            for child in alive:
                try:child.kill()
                except psutil.Error:pass
        except (OSError, psutil.Error):
            pass
        raise ProcessRegistrationError(str(exc)) from exc


class _CodexRpcConnection:
    """Multiplex RPC replies and notifications; never discard streamed events."""
    def __init__(self, cwd: Path, event: Callable[[dict], None] | None = None,
                 executable: str | None = None, tool_handler=None, launch_overrides=(),
                 send_initialized:bool=True, on_spawn=None, spawn_phase="codex-rpc", native_tool_calls=False):
        self.event = event or (lambda _: None)
        self.tool_handler = tool_handler
        self.native_tool_calls = native_tool_calls
        binary = executable or os.environ.get("LAPLACE_CODEX_BIN") or shutil.which("codex")
        if not binary:
            raise ProviderError("Codex CLI is not installed or not on PATH.")
        argv=[binary,"app-server","--stdio"]
        for override in launch_overrides or ():
            argv.extend(["-c",str(override)])
        self.process = subprocess.Popen(argv, cwd=cwd,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        bufsize=1, start_new_session=True)
        _publish_spawn(self.process, on_spawn, spawn_phase)
        self.pending: dict[int, queue.Queue] = {}
        self.lock = threading.Lock()
        self.next_id = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True, name="writing-codex-stream")
        self.reader.start()
        try:
            self.request("initialize", {"clientInfo": {"name": "laplace-writing", "version": "1"},
                                        "capabilities": {"experimentalApi": True}}, timeout=15)
            if send_initialized:self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise

    def send(self, obj: dict):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise ProviderError("Provider connection closed.")
            try:
                self.process.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise ProviderError("Provider connection closed while sending input.") from exc

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if "id" in obj and ("result" in obj or "error" in obj):
                    with self.lock:
                        waiter = self.pending.get(obj["id"])
                    if waiter:
                        waiter.put(obj)
                elif "id" in obj and "method" in obj:
                    if obj["method"] == "item/tool/call" and self.tool_handler:
                        def call(request=obj):
                            from contextlib import nullcontext
                            if self.native_tool_calls:
                                from laplace.writing import delivery
                                context = delivery.incoming(transport_kind="codex-appserver", request_id=request.get("id"))
                            else:
                                context = nullcontext(None)
                            with context as holder:
                                try:
                                    output = self.tool_handler(request.get("params") or {},
                                        **({"_incoming":holder} if holder is not None else {}))
                                except Exception as exc:
                                    result = {"success":False,"contentItems":[{"type":"inputText","text":str(exc)}]}
                                else:
                                    try:
                                        from laplace.projects.writing_sources import content_items
                                        result = {"success":True,"contentItems":content_items(output,"codex")}
                                    except Exception as exc:
                                        if holder is not None:delivery.delivery_uncertain(holder)
                                        result = {"success":False,"contentItems":[{"type":"inputText","text":str(exc)}]}
                                try:
                                    self.send({"id":request["id"],"result":result})
                                except ProviderError:
                                    if holder is not None:delivery.delivery_uncertain(holder)
                        threading.Thread(target=call, daemon=True, name="writing-project-tool").start()
                        continue
                    self.send({"id": obj["id"], "error": {"code": -32601,
                               "message": "This writing host does not implement the requested server callback."}})
                elif "method" in obj:
                    self.event(obj)
        except (OSError, ProviderError):
            pass
        finally:
            with self.lock:
                waiters = list(self.pending.values())
            for waiter in waiters:
                waiter.put({"error": {"message": "Provider process exited."}})
            self.event({"method": "connection/closed", "params": {}})

    def request(self, method: str, params: dict, timeout: float = 30):
        with self.lock:
            self.next_id += 1
            ident = self.next_id
            waiter = self.pending[ident] = queue.Queue()
        try:
            self.send({"id": ident, "method": method, "params": params})
            try:
                reply = waiter.get(timeout=timeout)
            except queue.Empty as exc:
                raise ProviderError(f"Provider timed out on {method}.") from exc
            if "error" in reply:
                raise ProviderError(str(reply["error"].get("message", reply["error"])))
            return reply.get("result", {})
        finally:
            with self.lock:
                self.pending.pop(ident, None)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)


def _codex_mcp_status(connection) -> list[dict]:
    """Bounded names/status/counts only; never retain server transport or credential values."""
    from laplace.writing import operating as writing_operating
    rows=[];cursor=None;seen=set()
    for _page in range(writing_operating.CODEX_MCP_STATUS_PAGES_MAX):
        params={"detail":"toolsAndAuthOnly","limit":100}
        if cursor is not None:params["cursor"]=cursor
        response=connection.request("mcpServerStatus/list",params,timeout=15)
        data=response.get("data")
        if not isinstance(data,list):
            raise ProviderError("Provider tool preflight returned no bounded server inventory.")
        for row in data:
            if not isinstance(row,dict) or not isinstance(row.get("name"),str):
                raise ProviderError("Provider tool preflight returned an unresolvable server row.")
            tools=row.get("tools")
            if not isinstance(tools,(dict,list)):
                raise ProviderError("Provider tool preflight returned an unresolvable tool inventory.")
            rows.append({"name":row["name"],"status":row.get("runtimeStatus"),
                         "tool_count":len(tools)})
            if len(rows)>writing_operating.CODEX_MCP_SERVERS_MAX:
                raise ProviderError("Provider tool preflight exceeded its server bound.")
        cursor=response.get("nextCursor")
        if cursor is None:return rows
        if not isinstance(cursor,str) or not cursor or cursor in seen:
            raise ProviderError("Provider tool preflight returned an invalid continuation.")
        seen.add(cursor)
    raise ProviderError("Provider tool preflight exceeded its page bound.")


def _codex_effective_mcp_config(connection,cwd:Path)->dict:
    """Effective MCP objects in memory only; callers project names/booleans and never emit values."""
    response=connection.request("config/read",{"cwd":str(Path(cwd).resolve()),
                                                "includeLayers":False},timeout=15)
    config=response.get("config") if isinstance(response,dict) else None
    if not isinstance(config,dict):raise ProviderError("Provider tool preflight could not read effective config.")
    servers=config.get("mcp_servers") or {}
    if not isinstance(servers,dict):raise ProviderError("Provider tool preflight found invalid server config.")
    for name,row in servers.items():
        if not isinstance(name,str) or not isinstance(row,dict):
            raise ProviderError("Provider tool preflight found unresolvable server config.")
    return servers


def _codex_configured_mcp_names(connection,cwd:Path)->list[str]:
    return list(_codex_effective_mcp_config(connection,cwd))


class CodexConnection:
    """A fail-closed App Server connection whose inherited MCP surface is empty."""
    def __init__(self,cwd:Path,event:Callable[[dict],None]|None=None,
                 executable:str|None=None,tool_handler=None,on_spawn=None,native_tool_calls=False):
        from laplace.writing import operating as writing_operating
        binary=executable or os.environ.get("LAPLACE_CODEX_BIN") or shutil.which("codex")
        if not binary:raise ProviderError("Codex CLI is not installed or not on PATH.")
        base=writing_operating.codex_process_config_overrides()
        probe=_CodexRpcConnection(cwd,executable=binary,launch_overrides=base,
                                  send_initialized=False,
                                  **({"on_spawn":on_spawn,"spawn_phase":"codex-preflight-probe"} if on_spawn else {}))
        try:
            names=_codex_configured_mcp_names(probe,cwd)
            controls=writing_operating.codex_process_config_overrides(names)
        except Exception:
            probe.close();raise
        probe.close()
        self._connection=_CodexRpcConnection(cwd,event,executable=binary,
            tool_handler=tool_handler,launch_overrides=controls,native_tool_calls=native_tool_calls,
            **({"on_spawn":on_spawn,"spawn_phase":"codex-serving"} if on_spawn else {}))
        try:
            effective=_codex_mcp_status(self._connection)
            effective_config=_codex_effective_mcp_config(self._connection,cwd)
            disabled={name for name,row in effective_config.items() if row.get("enabled") is False}
            enabled_or_unknown=set(effective_config)-disabled
            unresolved=[row for row in effective
                        if row["name"] not in disabled or row["tool_count"]!=0
                        or row["status"] not in (None,"disabled")]
            unresolved_names=set(names)-disabled
            if unresolved:
                raise ProviderError("Provider tool preflight left %d non-project server(s) unresolved."
                                    % len(unresolved))
            if unresolved_names:
                raise ProviderError("Provider tool preflight could not prove every resolved server disabled.")
            if enabled_or_unknown:
                raise ProviderError("Provider tool preflight found new or unresolved effective server config.")
            self.preflight={"resolved_names":len(names),"effective_rows":len(effective),
                            "disabled_names":len(disabled),"closed":True}
        except Exception:
            self._connection.close();raise

    @property
    def process(self):return self._connection.process

    def send(self,obj):return self._connection.send(obj)
    def request(self,method,params,timeout=30):return self._connection.request(method,params,timeout)
    def close(self):return self._connection.close()


_CAP_CACHE: tuple[float, dict] | None = None
_CAP_CACHE_ROOT: Path | None = None
_CAP_LOCK = threading.Lock()


def _claude_models(cwd:Path, *, on_spawn=None) -> list[dict]:
    """Discover this installation's catalogue through its SDK initialize reply.

    No user turn is sent, no session is persisted, and unrelated MCP servers are
    not loaded. The installed runtime decides aliases, models and effort levels.
    """
    request={'type':'control_request','request_id':'laplace-models',
             'request':{'subtype':'initialize','hooks':None,'skills':[]}}
    argv=['claude','-p','--input-format','stream-json','--output-format','stream-json',
          '--verbose','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence']
    from laplace.writing import operating as writing_operating
    # Discovery belongs to no session, so it runs in the workspaces root's own discovery
    # directory -- the same rule as a turn, with the same reason: this process must not read
    # the checkout's project documents either.  `cwd` stays the CHECKOUT the catalogue is
    # cached under (`_catalogue_path`).
    response=_metadata_run(argv,cwd=writing_operating.session_workspace(
                                writing_operating.DISCOVERY_SESSION),
                            input=json.dumps(request)+'\n', timeout=12, on_spawn=on_spawn, phase='claude-model-discovery')
    for line in response.stdout.splitlines():
        try:message=json.loads(line)
        except ValueError:continue
        reply=message.get('response') or {}
        if message.get('type')!='control_response' or reply.get('request_id')!='laplace-models':continue
        if reply.get('subtype')!='success':raise ValueError('Claude model discovery was refused')
        models=[]
        for item in (reply.get('response') or {}).get('models') or []:
            value=item.get('value');resolved=item.get('resolvedModel')
            if not isinstance(value,str) or not value:continue
            models.append({'id':'' if value=='default' else value,'resolved_model':resolved,
                'name':item.get('displayName') or value,'description':item.get('description') or '',
                'default':value=='default','supports_effort':bool(item.get('supportsEffort')),
                'efforts':item.get('supportedEffortLevels') or [],
                'context_window_advertised':1_000_000 if '[1m]' in (value+' '+str(resolved or '')) else None})
        if models:return models
    raise ValueError('Claude did not return a model catalogue')


def _metadata_run(argv, *, timeout, cwd=None, input=None, on_spawn=None, phase):
    """Metadata only. Publish ownership before sending metadata stdin."""
    if on_spawn is None:
        return subprocess.run(argv, cwd=cwd, input=input, capture_output=True, text=True, timeout=timeout)
    with subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE if input is not None else None,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        _publish_spawn(process, on_spawn, phase)
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate()
            raise
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _codex_capabilities(cwd, *, on_spawn=None):
    from laplace.writing import operating as writing_operating
    codex = {"id": "codex", "name": "Codex", "available": False, "executable": bool(shutil.which("codex")), "auth_state":"UNVERIFIED",
             "stream": True, "resume": True, "steer": True, "interrupt": True,
             "models": [], "error": None}
    if codex["executable"]:
        conn = None
        try:
            conn = CodexConnection(writing_operating.session_workspace(
                writing_operating.DISCOVERY_SESSION), **({"on_spawn":on_spawn} if on_spawn else {}))
            models = conn.request("model/list", {"limit": 100})
            codex["models"] = [{"id": m.get("model") or m.get("id"),
                                "name": m.get("displayName") or m.get("model") or m.get("id"),
                                "description": m.get("description") or "",
                                "default_effort": m.get("defaultReasoningEffort") or "medium",
                                "default": m.get("isDefault", False),
                                "efforts": [e.get("reasoningEffort") for e in m.get("supportedReasoningEfforts", [])],
                                "context_window_advertised": context_window_advertised("codex", m.get("model") or m.get("id") or "")}
                               for m in models.get("data", []) if not m.get("hidden")]
            codex["available"] = True; codex["auth_state"] = "READY"
        except ProcessRegistrationError:
            raise
        except Exception as exc:
            codex["error"] = str(exc)
            codex["auth_state"] = "UNAUTHENTICATED_OR_UNVERIFIED"
        finally:
            if conn:
                conn.close()
    return codex


def _claude_capabilities(cwd, *, on_spawn=None):
    claude_exe=bool(shutil.which('claude')); claude_auth='UNVERIFIED'; claude_available=False
    if claude_exe:
        try:
            probe=_metadata_run(['claude','auth','status','--json'],timeout=5,on_spawn=on_spawn,phase='claude-auth-discovery')
            safe=json.loads(probe.stdout or '{}') if probe.stdout else {}
            logged=bool(safe.get('loggedIn'))
            claude_auth='AUTHENTICATED_UNTESTED' if logged else 'UNAUTHENTICATED'
            claude_available=logged
        except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):
            claude_auth='UNVERIFIED'
    claude_models=[{"id":"","name":"Configured model","default":True,"efforts":["low","medium","high"]}]
    model_error=None
    if claude_available:
        try:claude_models=_claude_models(cwd, **({'on_spawn':on_spawn} if on_spawn else {}))
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:model_error=str(exc)
    return {"id": "claude", "name": "Claude", "available": claude_available, "executable": claude_exe, "auth_state":claude_auth,
                      "stream": True, "resume": True, "steer": False, "interrupt": True,
                      "models": claude_models,"model_discovery_error":model_error,
                      "custom_model": True,
                      "note": "Uses the installed Claude CLI and its account. Authentication must be verified before use."}


_PROVIDER_IDS = ('codex', 'claude')


def _catalogue_rows(value):
    """Unannotated existing catalogue rows, including their own observation qualification."""
    rows = json.loads(json.dumps(value.get('providers') or []))
    for row in rows:
        row.setdefault('observed_at', value.get('observed_at'))
        row.setdefault('model_observed_at', row['observed_at'] if (models_discovered(row)
            and row.get('model_catalogue_source') not in {'last-known-good', 'installed-cache'}) else None)
        for model in row.get('models') or []:
            model.pop('tier', None); model.pop('session_default', None)
    return {row['id']: row for row in rows}


def _capability_result(value, provider_id, *, cached=False):
    result = {**value, 'cached': cached}
    if provider_id is not None:
        selected = [row for row in value['providers'] if row['id'] == provider_id]
        result.update(providers=selected, observed_at=selected[0].get('observed_at'),
                      catalogue_observed_at=value.get('observed_at'),
                      observation_scope={'kind': 'provider', 'provider_id': provider_id})
    return with_model_choice(result)


def _merge_capabilities(previous, observed, provider_id):
    rows = _catalogue_rows(previous)
    for ident, row in observed.items():
        row = json.loads(json.dumps(row))
        prior = rows.get(ident) or {}
        failed = (row.get('error') or row.get('model_discovery_error') or not row.get('available') or not row.get('models'))
        if failed and prior.get('models'):
            row.update(models=prior['models'], model_catalogue_source='last-known-good',
                       model_observed_at=prior.get('model_observed_at'))
        rows[ident] = row
    now = time.time()
    return {'schema_version': 'laplace.provider-catalogue/1', 'providers': list(rows.values()),
            'observed_at': now if provider_id is None else previous.get('observed_at'), 'updated_at': now,
            'observation_scope': {'kind': 'catalogue'} if provider_id is None else {'kind': 'provider', 'provider_id': provider_id}}


def capabilities(cwd: Path, refresh: bool = False, *, provider_id: str | None = None, on_spawn=None) -> dict:
    """Discover only the selected provider, or the whole catalogue when selection is absent.

    Partial observation keeps each unselected row and the last whole-catalogue time.
    Memory reuse is both root- and provider-qualified; persisted rows remain passive metadata.
    """
    global _CAP_CACHE, _CAP_CACHE_ROOT
    if provider_id is not None and provider_id not in _PROVIDER_IDS:
        raise ProviderError('Unknown writing provider.')
    cwd = Path(cwd).resolve()
    with _CAP_LOCK:
        memory = provider_catalogue(cwd) if _CAP_CACHE and _CAP_CACHE_ROOT == cwd else None
        if not refresh and memory:
            if provider_id is None:
                stamp = memory.get('observed_at') if memory.get('observation_scope', {'kind':'catalogue'}).get('kind') == 'catalogue' else None
            else:
                stamp = next((row.get('observed_at') for row in memory.get('providers', []) if row['id'] == provider_id), None)
            if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and 0 <= time.time() - stamp < 600:
                return _capability_result(memory, provider_id, cached=True)
        previous = provider_catalogue(cwd)
        observed = {}
        for ident in (_PROVIDER_IDS if provider_id is None else (provider_id,)):
            row = (_codex_capabilities if ident == 'codex' else _claude_capabilities)(cwd, on_spawn=on_spawn)
            row['observed_at'] = time.time()
            row['model_observed_at'] = row['observed_at'] if (row.get('available') and not row.get('error')
                and not row.get('model_discovery_error') and models_discovered(row)) else None
            observed[ident] = row
        value = _merge_capabilities(previous, observed, provider_id)
        try:
            from filelock import FileLock, Timeout
            path = _catalogue_path(cwd)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Merge after discovery under the existing catalogue's writer lock. A concurrent
            # observation of the other provider is not replaced by our earlier snapshot.
            with FileLock(str(path) + '.lock', timeout=2):
                value = _merge_capabilities(provider_catalogue(cwd), observed, provider_id)
                temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
                temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, path)
        except (OSError, Timeout):
            # Persistence is optional; this exact in-process observation remains qualified.
            pass
        _CAP_CACHE = (time.monotonic(), value)
        _CAP_CACHE_ROOT = cwd
        return _capability_result(value, provider_id)


def writing_operating_door() -> str:
    """The door's one name, from the contract, never spelled in an adapter."""
    from laplace.writing import operating as writing_operating
    return writing_operating.DOOR_TOOL


# Interpreter selectors an inherited environment could use to load a different code owner or a startup hook in
# the native tool child. HOME, CODEX_HOME, credentials and every other variable are kept unchanged.
_UNSAFE_CODE_SELECTORS = ('PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT', 'PYTHONUSERBASE', 'PYTHONEXECUTABLE', 'PYTHONPLATLIBDIR')


def native_code_environment(environ=None) -> dict:
    """The environment for a native tool child (`sys.executable -m laplace.native.tools`): its imports resolve to the
    package THIS process actually loaded (laplace.core.checkout.package_root().parent), on the same selected runtime,
    never to the --root project data, the provider or child working directory, a user site or an inherited
    PYTHONPATH. Only Python source selectors change; HOME/CODEX_HOME, authority and data roots are untouched."""
    from laplace.core import checkout
    env = dict(os.environ if environ is None else environ)
    for key in _UNSAFE_CODE_SELECTORS:
        env.pop(key, None)
    env['PYTHONPATH'] = str(checkout.package_root().parent)
    env['PYTHONSAFEPATH'] = '1'      # the child's cwd never precedes the bound code owner
    env['PYTHONNOUSERSITE'] = '1'    # no user site-packages can shadow it
    return env


class WritingTurn:
    """One live turn. Native conversation ID survives the on-demand connection."""
    def __init__(self, cwd: Path, provider: str, model: str, effort: str,
                 native_id: str | None, event: Callable[[dict], None], mode="discuss", project=None,
                 logical_turn_id=None, native_source_paths=None, session_id=None):
        from laplace.writing import operating as writing_operating
        if provider not in ("codex", "claude"):
            raise ProviderError("Unknown writing provider.")
        # EFFORT TRUTH (S2): `None` is a recorded effort -- the one a model that supports no
        # effort is sent, which is no flag at all.  The session row carries what was sent
        # instead of the compatibility value `medium` (the live row
        # WS-abc8cfa1d95c4828bc49aacbd93b81b8 banks haiku with effort 'medium' while this
        # transport sent no flag), and a pane may still display Automatic.
        if effort is not None and effort not in ("low", "medium", "high", "xhigh", "max", "ultra"):
            raise ProviderError("Unsupported effort.")
        self.cwd, self.provider, self.model, self.effort = Path(cwd).resolve(), provider, model, effort
        # `cwd` is THE CHECKOUT and keeps that meaning: the door's root, the brief's root
        # and the base of this turn's native source paths.  `workspace` is where the
        # PROCESS runs, which is no longer the same directory
        # (writing_operating.session_workspace).  One name per fact.
        self.session_id = session_id
        self.workspace = writing_operating.session_workspace(session_id)
        self.native_id, self.event, self.mode = native_id, event, mode
        self.project = project
        self.logical_turn_id = logical_turn_id
        self.native_source_paths = {Path(path).resolve() for path in (native_source_paths or [])}
        self.context_window_advertised = context_window_advertised(provider, model)
        self.context_window_effective = None
        self.conn = None
        self.process = None
        self.turn_id = None
        self.usage_facts = _UsageFacts(provider,self.cwd,logical_turn_id,model)
        self.delivery = None
        self.inference_started = False
        self.cancelled = threading.Event()
        self._reader_interrupt_lock = threading.Lock()

    def run(self, prompt: str) -> dict:
        if getattr(self, 'reader_profile', None) and self.provider != 'claude':
            raise ProviderError('Sealed text reader supports only the qualified Claude profile.')
        return self._codex(prompt) if self.provider == "codex" else self._claude(prompt)

    def interrupt(self):
        from laplace.writing.sealed_reader import operator_profile
        operator=operator_profile(getattr(self,'reader_profile',None))
        if operator:
            with self._reader_interrupt_lock:
                if self.cancelled.is_set():return {}
                return self._interrupt(operator['limits']['cleanup_grace_seconds'])
        return self._interrupt(3)

    def _interrupt(self,grace):
        self.cancelled.set()
        if self.conn and self.turn_id:
            return self.conn.request("turn/interrupt", {"threadId": self.native_id, "turnId": self.turn_id})
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            def kill_if_needed():
                try:
                    self.process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    try:os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:pass
            threading.Thread(target=kill_if_needed, daemon=True).start()
        return {}

    def control_capabilities(self) -> dict:
        if getattr(self, 'reader_profile', None):
            return {'can_interrupt':True, 'can_steer':False, 'can_offer_input':False, 'input_delivery_modes':[]}
        native=self.provider == "codex" and self.conn is not None and self.turn_id is not None
        return {"can_interrupt": True,"can_steer":native,"can_offer_input":bool(self.project),
                "input_delivery_modes":(["native_rpc"] if native else [])+(["project_tool_boundary"] if self.project else [])}

    def steer(self, text: str):
        if self.provider != "codex" or not self.conn or not self.turn_id:
            raise ProviderError("This provider cannot accept steering in the current turn. Stop it or wait for its reply.")
        return self.conn.request("turn/steer", {"threadId": self.native_id,
                                 "expectedTurnId": self.turn_id,
                                 "input": [{"type": "text", "text": text}]})

    def _codex(self, prompt: str) -> dict:
        from laplace.writing import operating as writing_operating
        policy = writing_operating.session_policy()
        arguments = policy["transport_arguments"]["codex"]
        done = threading.Event()
        chunks, final_messages, outcome, native_file_changes = [], {}, {}, []
        usage = None
        event_lock = threading.Lock()
        pending_events = []

        def consume_event(obj):
            nonlocal usage
            method, params = obj.get("method"), obj.get("params") or {}
            event_turn = ((params.get("turn") or {}).get("id")
                          if method in {"turn/started", "turn/completed"}
                          else params.get("turnId"))
            if event_turn != self.turn_id:
                return
            if method == "item/agentMessage/delta":
                delta = params.get("delta", "")
                chunks.append(delta)
                self.event({"type": "delta", "text": delta})
            elif method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage" and item.get("phase") in (None, "final", "final_answer"):
                    final_messages[item.get("id", "final")] = item.get("text", "")
                elif item.get("type") == "fileChange":
                    for change in item.get("changes") or []:
                        path = change.get("path") if isinstance(change, dict) else None
                        if not isinstance(path, str):
                            continue
                        candidate = Path(path)
                        resolved = (candidate if candidate.is_absolute() else self.cwd / candidate).resolve()
                        if resolved in self.native_source_paths:
                            native_file_changes.append({"path": str(resolved),
                                                        "kind": change.get("kind"),
                                                        "status": item.get("status")})
            elif method == "turn/completed":
                outcome.update(params.get("turn") or {})
                self.usage_facts.codex((params.get('turn') or {}).get('tokenUsage'),'terminal')
                reported = _codex_token_usage((params.get("turn") or {}).get("tokenUsage"))
                if reported is not None:
                    usage = reported
                done.set()
            elif method == "thread/tokenUsage/updated":
                self.usage_facts.codex(params.get('tokenUsage'))
                reported = _codex_token_usage(params.get("tokenUsage"))
                if reported is not None:
                    usage = reported
                    self.context_window_effective = context_window_max("codex", self.model, {"thread_token_usage": usage})
                    usage_event = usage_projection("codex", usage, self.context_window_effective)
                    facts_view=self.usage_facts.snapshot()
                    self.event({"type": "usage", "usage": usage_event,
                                "context_window_advertised": self.context_window_advertised,
                                "context_window_effective": self.context_window_effective,
                                "context_tokens_used": facts_view["selected"]["context_snapshot"]["value"],
                                "usage_selection": usage_facts_projection(facts_view)})
            elif method == 'model/rerouted':
                self.usage_facts.model(params.get('toModel'),'model/rerouted',actual=True)
            elif method in ("item/started", "turn/started"):
                item = params.get("item") or {}
                self.event({"type": "progress", "text": item.get("type", "Working")})

        def on_event(obj):
            method, params = obj.get("method"), obj.get("params") or {}
            with event_lock:
                if method == "connection/closed":
                    if not done.is_set():
                        outcome.update(status="failed", error={"message": "Provider connection ended before completion."})
                        done.set()
                    return
                if method not in {"item/agentMessage/delta", "item/completed", "turn/completed", "thread/tokenUsage/updated",
                                  "item/started", "turn/started", "model/rerouted"}:
                    return
                # A connection also receives notifications from descendant
                # threads. Their replies and completion cannot finish this turn.
                if not self.native_id or params.get("threadId") != self.native_id:
                    return
                if self.turn_id is None:
                    # Notifications can precede the turn/start RPC response.
                    # Wait for its authoritative ID before accepting any of them.
                    pending_events.append(obj)
                else:
                    consume_event(obj)

        def tool_call(params, *, _incoming=None):
            if params.get("tool") != writing_operating_door() or params.get("threadId") != self.native_id:
                raise ProviderError("Project tool does not belong to this writing session.")
            from laplace.native.tools import call
            fields = params.get("arguments", {})
            operation = fields.get("operation") if isinstance(fields, dict) else None
            payload = (fields.get("payload") or {}) if isinstance(fields, dict) else {}
            self.event({"type":"progress","text":"Project: " + str(operation or (fields.get("verb") if isinstance(fields,dict) else "invalid arguments"))})
            try:
                return call(self.cwd, self.project, self.mode, fields,
                               turn_id=self.logical_turn_id, _incoming=_incoming)
            except Exception as exc:
                # The row and its bound belong to the ONE producer
                # (writing_tools.tool_failure); this handler owns only the App Server's
                # own error channel.  It used to bank an unbounded payload of its own.
                from laplace.native.tools import tool_failure
                recovery=tool_failure(self.cwd,self.project,self.mode,operation,payload,exc,
                                      self.logical_turn_id,provider="codex")
                from laplace.writing import delivery
                error=ValueError(json.dumps(recovery,ensure_ascii=False,default=str))
                state=delivery.carried(exc)
                if state:delivery.carry(error,state)
                raise error from exc
        # The app server starts in the empty session workspace, not in the checkout:
        # the process reads AGENTS.md and `.codex` out of its own working directory.
        self.conn = CodexConnection(self.workspace, on_event, tool_handler=tool_call if self.project else None,
            native_tool_calls=bool(self.project),
            **({"on_spawn":self.on_spawn} if getattr(self,"on_spawn",None) else {}))
        try:
            if self.model:
                listing=self.conn.request('model/list',{'limit':100})
                selected=next((m for m in listing.get('data',[]) if (m.get('model') or m.get('id'))==self.model),None)
                if not selected:
                    raise ProviderError(f"Unknown Codex model {self.model!r}; refresh provider capabilities.")
                efforts=[e.get('reasoningEffort') for e in selected.get('supportedReasoningEfforts',[]) if e.get('reasoningEffort')]
                if efforts and self.effort is not None and self.effort not in efforts:
                    raise ProviderError(f"Codex model {self.model!r} does not support effort {self.effort!r}; supported: {', '.join(efforts)}")
            # Every session parameter below is the contract's, spelled for this
            # transport by the policy: approval `never` is its `interactive_approval:
            # none`, and sandbox `read-only` is its `write_authority.outside_the_door:
            # none`.  The sandbox was `workspace-write` with `network_access: True` and
            # `web_search: live`, which gave this transport two write and read routes the
            # Claude transport is refused and the ledger never saw.
            # The thread's own cwd is the same empty workspace; the DOOR still reads the
            # checkout (`execute(self.cwd, ...)` in tool_call above).
            params = {"cwd": str(self.workspace),
                      "approvalPolicy": arguments["approvalPolicy"],
                      "sandbox": arguments["sandbox"]}
            if self.project:
                brief = getattr(self,"operating_brief",None) or writing_operating.build(self.project,self.mode,self.cwd)
                # The whole app-owned config, from the contract. Capacity and compaction are
                # provider-owned and arrive later as labelled telemetry; the app does not turn
                # its catalogue maximum into an arbitrary window or cutoff. Web search is
                # explicitly disabled because dynamicTools do not replace App Server's native
                # surface and omission would not establish network closure.
                # The subsequent usage event remains the sole effective-window observation.
                params["config"] = writing_operating.codex_session_config()
                # The shared builder supplies the app kernel in the base slot and the
                # project body/current frame in the user channel. Only the tool alias varies.
                blocks = writing_operating.process_instructions(
                    brief, "codex", resumed=bool(self.native_id))
                self.delivery=writing_operating.delivery_receipt(brief,"codex",prompt,resumed=bool(self.native_id))
                if blocks["session_slot"]:
                    params["baseInstructions"] = blocks["session_slot"]
                    params["developerInstructions"] = ""
                turn_prefix = blocks["turn_prefix"]
            if self.model:
                params["model"] = self.model
            if self.native_id:
                params["threadId"] = self.native_id
            elif self.project:
                from laplace.native.tools import specification
                params["dynamicTools"] = [specification()]
            # BOTH branches: a resumed thread's parameters are a subset of a start's today,
            # so checking only the start is how a parameter added to the resume path alone
            # would escape the declaration.
            complaints = writing_operating.argument_complaints(
                "codex", "thread_parameters", params,
                {"project": bool(self.project), "resume": bool(self.native_id),
                 "model": bool(self.model), "revise": self.mode == "revise"})
            if complaints:
                raise ProviderError("Thread parameter(s) outside the declaration: "
                                    + "; ".join(complaints))
            resumed=bool(self.native_id)
            response = self.conn.request("thread/resume" if resumed else "thread/start",
                                         params)
            returned_id=response['thread']['id']
            if resumed and returned_id!=self.native_id:
                raise ProviderError('Resumed provider thread does not match the admitted binding.')
            self.native_id = returned_id
            resolved_model = response.get("model") or self.model
            self.usage_facts.bind(self.native_id,fresh=not resumed)
            self.usage_facts.model(resolved_model,'thread_response_model')
            native_path=response['thread'].get('path');native_start=None;native_stamp=None
            if isinstance(native_path,str):
                candidate=Path(native_path)
                if candidate.is_absolute() and self.native_id in candidate.name and not candidate.is_symlink():
                    try:
                        stat=candidate.stat();native_start=stat.st_size;native_stamp=(stat.st_dev,stat.st_ino)
                    except OSError:pass
            if self.delivery:
                if not resumed:self.delivery['parts']['kernel']['state']='SENT'
                self.delivery['request_fingerprints']={'thread_parameters':writing_operating.digest(params)}
            self.event({"type": "session", "native_id": self.native_id,
                        "model": resolved_model, "provider": "codex",
                        # The same receipt on this transport: the cwd the thread was
                        # started with, and the preflight that proved the inherited MCP
                        # surface closed before the thread existed (CodexConnection
                        # :402-404).  There is no init event here, so the thread
                        # parameters this adapter sent ARE the observation.
                        "process": {"workspace": str(self.workspace),
                                    "cwd": params.get("cwd"),
                                    "preflight": getattr(self.conn, "preflight", None)},
                        "delivery_receipt": self.delivery})
            if self.cancelled.is_set():
                return turn_output(policy, {"status": "interrupted", "text": "",
                                            "native_id": self.native_id,
                                            "resolved_model": resolved_model})
            if self.project:
                # The turn's own frame: the mode, the role, the permissions and the response
                # contract, with EVERY turn, because a session changes mode and a thread's
                # instructions cannot.  Decided above, by the contract, before `thread/start`
                # replaced `self.native_id` with this thread's id.
                prompt = turn_prefix + writing_operating.BLOCK_JOIN + prompt
            turn_params = {"threadId": self.native_id, "input": [{"type": "text", "text": prompt}],
                           # EFFORT TRUTH: a model with no effort control is sent no effort
                           # key at all, the same rule as the Claude transport's `--effort`.
                           **({"effort": self.effort} if self.effort is not None else {})}
            if self.model:
                turn_params["model"] = self.model
            if self.mode == "revise":
                turn_params["outputSchema"] = EDIT_SCHEMA
            complaints = writing_operating.argument_complaints(
                "codex", "turn_parameters", turn_params,
                {"project": bool(self.project), "resume": True,
                 "model": bool(self.model), "revise": self.mode == "revise"})
            if complaints:
                raise ProviderError("Turn parameter(s) outside the declaration: "
                                    + "; ".join(complaints))
            self.inference_started = True
            started = self.conn.request("turn/start", turn_params)
            with event_lock:
                self.turn_id = started["turn"]["id"]
                self.usage_facts.bind(self.native_id,self.turn_id)
                if self.delivery:
                    for name in ("body","frame","task"):
                        if self.delivery["parts"][name]["state"]=="PREPARED":self.delivery["parts"][name]["state"]="SENT"
                    self.delivery["request_fingerprints"]["turn_parameters"]=writing_operating.digest(turn_params)
                for early in pending_events:
                    consume_event(early)
                pending_events.clear()
            self.event({"type": "turn", "turn_id": self.turn_id})
            while not done.wait(0.25):
                if self.cancelled.is_set():
                    self.interrupt()
                    if not done.wait(10):
                        outcome["status"] = "interrupted"
                        break
            text = "\n\n".join(final_messages.values()) or "".join(chunks)
            values = {"status": outcome.get("status", "failed"), "text": text,
                      "native_id": self.native_id, "turn_id": self.turn_id,
                      "resolved_model": resolved_model, "error": outcome.get("error"),
                      "native_file_changes": native_file_changes or None,
                      "context_window_advertised": self.context_window_advertised,
                      "context_window_effective": self.context_window_effective}
            self.usage_facts.native_codex(native_path,native_start,native_stamp)
            values['usage_facts']=self.usage_facts.snapshot()
            values['usage_basis']={'counter_scope':'last_request','basis':'codex.appserver.last','counter_domain':'main_conversation'}
            if self.delivery:values['delivery_receipt']=self.delivery
            projected = usage_projection("codex", usage, self.context_window_effective)
            if projected is not None:
                values["usage"] = projected
                context_selection=values["usage_facts"]["selected"]["context_snapshot"]
                values["context_tokens_used"] = context_selection["value"] if context_selection else None
            if self.mode == "revise" and values["status"] == "completed":
                try:
                    values["proposal"] = json.loads(list(final_messages.values())[-1] if final_messages else text)
                except (ValueError, IndexError):
                    values["error"] = {"message": "The provider did not return a valid edit proposal. Nothing was applied."}
            return turn_output(policy, values)
        finally:
            self.conn.close()

    def sends_effort(self) -> bool:
        """Whether this turn sends an effort flag: the ONE predicate the argv appends by and
        the declaration is checked against.  They used to differ -- the argv appended
        ``--effort`` only when an effort existed, the declaration demanded it whenever the
        model supported effort -- so a session recorded with effort ``None`` (what a model
        without effort control is sent) on an installation whose live catalogue did not
        advertise that model refused to start: "--effort is required (effort) and was not
        sent" (ux/m5-live-pilot-friction.json HAIKU_REQUIRED_EFFORT).  No effort recorded
        means no flag sent, and no flag sent is the declared occasion."""
        return self.effort is not None and bool(getattr(self, 'supports_effort', True))

    def _claude(self, prompt: str) -> dict:
        binary = shutil.which("claude")
        if not binary:
            raise ProviderError("Claude CLI is not on PATH.")
        from laplace.writing import operating as writing_operating
        reader = getattr(self, 'reader_profile', None)
        operator = None
        if reader:
            from laplace.writing import sealed_reader
            policy={'turn_output':{'required':writing_operating.TURN_OUTPUT_REQUIRED,
                                   'optional':writing_operating.TURN_OUTPUT_OPTIONAL}}
            if self.native_id:
                raise ProviderError('Sealed reader profile changed or attempted a native resume.')
            startup_basis=sealed_reader.execution_support(self.cwd,self.project,reader)
            operator=sealed_reader.operator_profile(reader)
            argv = [binary, *sealed_reader.claude_arguments(self.model, self.effort,operator)]
            sealed_reader.validate_arguments(argv[1:], self.model, self.effort,operator)
            if operator:self.reader_operator_argv=list(argv)
            self.delivery = writing_operating.delivery_receipt(self.operating_brief, 'claude', prompt, resumed=False)
            self.delivery['reader'] = {'profile': sealed_reader.PROFILE, 'state': 'PREPARED',
                'fingerprint': reader['fingerprint'], 'inventory_observed': False}
            if operator:self.delivery['reader']['operator']={'purpose':operator['purpose'],'limits':operator['limits']}
            if operator:
                raw=prompt.encode('utf-8')
                from laplace.core.identity import bytes_digest
                if (bytes_digest(raw)!=operator['stdin_sha256'] or len(raw)!=operator['stdin_utf8_bytes']
                        or len(raw)+len(sealed_reader.KERNEL.encode())!=operator['input_utf8_bytes']
                        or operator['input_utf8_bytes']>operator['limits']['max_input_utf8_bytes']):
                    raise ProviderError('Operator input differs from its exact admitted complete bytes.')
            admitted_native_id = None
        else:
            policy = writing_operating.session_policy()
            # The approval stance and the withdrawal of the native tool surface are the
            # policy's `interactive_approval: none` and `write_authority.outside_the_door:
            # none`, spelled for this transport in ONE place.  They used to be an argv literal
            # here, which is why nothing could compare them with the Codex sandbox.
            # Includes only the invocation-local default output style; no global edit.
            argv = [binary, *writing_operating.transport_argv("claude")]
            if self.sends_effort():argv.extend(['--effort',self.effort])
            if self.project:
                brief = getattr(self,"operating_brief",None) or writing_operating.build(self.project,self.mode,self.cwd)
                # The CLI reconstructs its system prompt in every process and --resume retains
                # conversation messages, not this appended slot.  So the KERNEL rides here on
                # every process -- the same bytes, which the contract requires and the harness
                # checks -- and the project BODY rides ONCE, in the first user turn, which
                # --resume does retain.  It used to send the whole brief unconditionally:
                # 180,358 characters over the eight resumed processes of one measured corpus.
                # Which blocks THIS process carries is the contract's one rule, read here and in
                # the Codex transport from the same function; the two `if not self.native_id`
                # guards it replaces were two spellings of it.
                blocks = writing_operating.process_instructions(
                    brief, "claude", resumed=bool(self.native_id))
                # The kernel is the WHOLE system prompt, not an appendix to the CLI's own, and
                # the CLI's dynamic sections are excluded with it.  Both flags are declared
                # together in `TRANSPORT_ARGUMENTS` (writing_operating.py:188-190, the two keys,
                # beneath the measurement that chose them); `argument_complaints` below checks this argv
                # against that declaration, which is why the names are not a second rule.
                self.delivery=writing_operating.delivery_receipt(brief,"claude",prompt,resumed=bool(self.native_id))
                argv += ["--system-prompt", blocks["session_slot"],
                         "--exclude-dynamic-system-prompt-sections"]
                prompt = blocks["turn_prefix"] + writing_operating.BLOCK_JOIN + prompt
            if self.project:
                import sys
                mcp = {"mcpServers": {"laplace": {"command": sys.executable,
                        "args": ["-m", "laplace.native.tools", "--root", str(self.cwd),
                                 "--project", self.project, "--mode", self.mode, "--turn-id", self.logical_turn_id or ""]}}}
                if getattr(self,'connected_observation',None):
                    # Installed Claude declares per-server timeout in milliseconds;
                    # this is invocation-local author observation, never child lifetime.
                    mcp['mcpServers']['laplace']['timeout']=self.connected_observation['transport_timeout_ms']
                argv += ["--mcp-config", json.dumps(mcp), "--strict-mcp-config"]
                # The app has already authorized this project-bound gateway. Native
                # CLI permission prompts have no answering host in this transport;
                # requiring one here silently prevents even ordinary source reads.
                argv += ["--allowedTools", policy["tool"]["visible_name"]["claude"]]
            admitted_native_id=self.native_id
            if self.native_id:
                argv += ["--resume", self.native_id]
            if self.model:
                argv += ["--model", self.model]
            if self.mode == "revise":
                argv += ["--json-schema", json.dumps(EDIT_SCHEMA)]
            # The whole argv against the whole declaration: every required argument present, each
            # declared argument once, and every value one the declaration permits.  The check
            # this replaces compared a SET of tokens, so a declared flag repeated with an
            # undeclared value (`--permission-mode bypassPermissions` after the declared pair,
            # which the CLI resolves in favour of the LAST occurrence) and a REQUIRED flag
            # deleted (`--strict-mcp-config`) both passed it.
            complaints = writing_operating.argument_complaints(
                "claude", "argv", argv[1:],
                {"project": bool(self.project), "resume": bool(self.native_id),
                 "model": bool(self.model), "revise": self.mode == "revise",
                 "effort": self.sends_effort()})
            if complaints:
                raise ProviderError("Process argument(s) outside the declaration: "
                                    + "; ".join(complaints))
        # The CLI spawns the native tool child (sys.executable -m laplace.native.tools --root <project data>) with this
        # environment: bind its imports to the actually loaded code owner, independent of --root, cwd and inherited paths.
        env = native_code_environment(os.environ)
        env.pop("CLAUDECODE", None)
        try:
            with self._reader_interrupt_lock if operator else nullcontext():
                if operator and self.cancelled.is_set():
                    return turn_output(policy,{'status':'interrupted','text':'','native_id':None,'turn_id':None})
                self.process = subprocess.Popen(argv, cwd=self.workspace, env=env, stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                text=True, encoding="utf-8", start_new_session=True)
                _publish_spawn(self.process, getattr(self,"on_spawn",None), "claude-serving",
                    cleanup_grace=operator['limits']['cleanup_grace_seconds'] if operator else 3)
            self.inference_started = True
            self.process.stdin.write(prompt)
            self.process.stdin.close()
            if self.delivery:
                for part in self.delivery['parts'].values():
                    if part['state']=='PREPARED':part['state']='SENT'
                self.delivery['request_fingerprints']={'argv':writing_operating.digest(argv[1:]),'stdin':writing_operating.digest(prompt)}
            chunks, message, result, assistant_usage, assistant_model = [], "", {}, None, None
            operator=sealed_reader.operator_profile(reader) if reader else None
            streamed_bytes=0
            def public_prefix(text,limit):
                value,clipped=sealed_reader.byte_prefix(text,limit)
                if clipped:
                    self.reader_limit_reason='operator-public-output-bytes';self.interrupt()
                return value
            pending_text_message = False
            for line in self.process.stdout:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") == "system" and obj.get("subtype") == "init":
                    if admitted_native_id and obj.get('session_id')!=admitted_native_id:
                        raise ProviderError('Provider init does not match the admitted session binding.')
                    self.native_id = obj.get("session_id")
                    self.usage_facts.bind(self.native_id)
                    self.usage_facts.model(obj.get('model'),'init_model')
                    if self.delivery:
                        if reader:
                            observed = sealed_reader.observe_startup(obj,executable_sha256=startup_basis['executable_sha256'])
                            self.delivery['reader'] = observed
                            self.delivery['native_inventory'] = {'state':'OBSERVED' if all(
                                state in {'OBSERVED_EMPTY','OFFERED'} for state in observed['offered_capabilities'].values()) else 'UNOBSERVABLE', 'tool_count': observed['counts']['tools'],
                                'mcp_count': observed['counts']['mcp_servers']}
                            if observed['state'] == 'UNQUALIFIED':
                                raise ProviderError('Sealed reader startup reported an unsupported capability or effective-context boundary.')
                        else:
                            self.delivery['native_inventory']={'state':'OBSERVED','tools':obj.get('tools'),
                                'mcp_servers':[row.get('name') if isinstance(row,dict) else str(row) for row in obj.get('mcp_servers') or []]}
                            self.delivery['platform_extra_instructions']['reported_customizations']=_claude_init_customizations(obj)
                    # WHAT THIS PROCESS WAS ACTUALLY GIVEN, from the runtime's own init
                    # event, riding the one event that already reaches the row bank: the
                    # tool inventory it reports, the MCP servers it loaded, and the
                    # directory it is running in.  Declaring the closure is not observing
                    # it, and `--tools ""` is a request; this is the receipt.
                    servers = [] if reader else obj.get("mcp_servers")
                    self.event({"type": "session", "native_id": self.native_id,
                                "model": obj.get("model", self.model), "provider": "claude",
                                "process": {"workspace": str(self.workspace),
                                            "cwd": str(self.workspace) if reader else obj.get("cwd"),
                                            "tools": [] if reader else obj.get("tools"),
                                            "mcp_servers": sorted(
                                                str(row.get("name") if isinstance(row, dict) else row)
                                                for row in (servers or []))
                                            if isinstance(servers, list) else servers},
                                "delivery_receipt": self.delivery})
                if reader:
                    event = obj.get('event') or {}
                    blocks = (obj.get('message') or {}).get('content') or []
                    attempted = event.get('content_block', {}).get('type') in {'tool_use','server_tool_use'} or any(
                        isinstance(block, dict) and block.get('type') in {'tool_use','server_tool_use'} for block in blocks)
                    if attempted or (obj.get('type') == 'result' and obj.get('permission_denials')):
                        self.delivery['reader'] = {'profile': sealed_reader.PROFILE, 'state':'UNQUALIFIED',
                            'reason':'A tool call was attempted on the tool-less profile.'}
                        raise ProviderError('Sealed reader attempted a tool call; isolation is unqualified.')
                if operator:
                    maximum=operator['limits']['max_output_utf8_bytes']
                    if obj.get('type')=='stream_event':
                        delta=(obj.get('event') or {}).get('delta') or {}
                        if delta.get('type')=='text_delta' and isinstance(delta.get('text'),str):
                            delta['text']=public_prefix(delta['text'],max(0,maximum-streamed_bytes))
                            streamed_bytes+=len(delta['text'].encode())
                    if obj.get('type')=='assistant':
                        snapshot=obj.get('message') or {};blocks=snapshot.get('content') or []
                        text='\n'.join(row.get('text','') for row in blocks if row.get('type')=='text')
                        bounded=public_prefix(text,maximum)
                        if bounded!=text:snapshot['content']=[{'type':'text','text':bounded}]
                    if obj.get('type')=='result' and isinstance(obj.get('result'),str):
                        obj['result']=public_prefix(obj['result'],maximum)
                if obj.get("type") == "stream_event":
                    if obj.get("parent_tool_use_id") is not None:
                        continue
                    event = obj.get("event") or {}
                    if event.get("type") == "message_start":
                        pending_text_message = True
                    elif event.get("type") == "message_stop":
                        pending_text_message = False
                    delta = event.get("delta") or {}
                    text_delta = delta.get("text", "")
                    if delta.get("type") == "text_delta" and text_delta:
                        # Keep the native message boundary, but publish it only
                        # when visible text begins. Thinking/tool-only messages
                        # must not create blank paragraphs in the conversation.
                        if pending_text_message:
                            self.event({"type": "progress", "text": "agentMessage"})
                            prior = "".join(chunks)
                            if prior and not prior.endswith("\n\n"):
                                separator = "\n" if prior.endswith("\n") else "\n\n"
                                if operator:
                                    separator=public_prefix(separator,max(0,operator['limits']['max_output_utf8_bytes']-streamed_bytes))
                                    streamed_bytes+=len(separator.encode())
                                chunks.append(separator)
                                # The final result already preserved this native
                                # assistant-message boundary. Stream the same
                                # separator so the live transcript cannot fuse
                                # successive messages while the turn is active.
                                self.event({"type": "delta", "text": separator})
                            pending_text_message = False
                        chunks.append(text_delta)
                        self.event({"type": "delta", "text": text_delta})
                if obj.get("type") == "assistant":
                    # Subagents carry parent_tool_use_id; their model/usage cannot
                    # describe this writing conversation's context window.
                    if obj.get("parent_tool_use_id") is not None:
                        continue
                    assistant = obj.get("message") or {}
                    message = "\n".join(b.get("text", "") for b in assistant.get("content", []) if b.get("type") == "text")
                    if str(assistant.get("model") or "").startswith("<"):
                        # Local CLI errors can arrive as synthetic assistant
                        # messages with zero usage. They are not a new model
                        # observation and must not erase the last real context.
                        continue
                    if isinstance(assistant.get("model"), str) and assistant["model"]:
                        assistant_model = assistant["model"]
                    self.usage_facts.claude_assistant(assistant)
                    reported = _claude_assistant_usage(assistant.get("usage"))
                    if reported is not None:
                        # Fold this round trip's own output into the TURN's running total
                        # (one visible reply can span several round trips); the live
                        # streamed event still projects each round trip's own report, since
                        # that is what was observed at that moment.
                        assistant_usage = reported # latest observed request, never summed duplicate emissions
                        usage_event = usage_projection("claude", reported,
                                                       self.context_window_effective)
                        facts_view=self.usage_facts.snapshot()
                        self.event({"type": "usage", "usage": usage_event,
                                    "context_window_advertised": None,
                                    "context_window_effective": None,
                                    "context_tokens_used": facts_view["selected"]["context_snapshot"]["value"],
                                    "usage_selection": usage_facts_projection(facts_view)})
                if obj.get("type") == "result":
                    result = obj
            code = self.process.wait(timeout=operator['limits']['cleanup_grace_seconds']+1 if operator else 5)
            if reader and self.delivery['reader']['state']!=sealed_reader.STARTUP_STATE:
                self.delivery['reader']={'profile':sealed_reader.PROFILE,'state':'UNQUALIFIED',
                    'reason':'Required offered-capability observation was not seen.'}
                if not self.cancelled.is_set():
                    raise ProviderError('Sealed reader startup inventory was not observed.')
            model_usage = _claude_model_usage(result)
            if model_usage is not None:
                self.context_window_effective = context_window_max("claude", assistant_model or self.model,
                                                                    {"model_usage": model_usage})
            values = {"status": "interrupted" if self.cancelled.is_set() else
                      "completed" if code == 0 and not result.get("is_error") else "failed",
                      "text": result.get("result") or message or "".join(chunks),
                      "native_id": self.native_id, "proposal": result.get("structured_output"),
                      "error": result.get("errors") if result.get("is_error") else None,
                      # A CLI turn is a process and has no provider turn identity to report;
                      # the policy declares the key and it is null here rather than absent.
                      "turn_id": None,
                      "resolved_model": assistant_model or self.model,
                      "context_window_advertised": self.context_window_advertised,
                      "context_window_effective": self.context_window_effective}
            if operator:
                values['text']=public_prefix(values['text'],operator['limits']['max_output_utf8_bytes'])
                values['proposal']=None
            if values["status"] == "failed" and not values.get("error"):
                values["error"] = values["text"] or f"Claude exited with status {code}."
            issues = []
            for denied in result.get("permission_denials") or []:
                fields = denied.get("tool_input") or {}
                issue = {"tool_name": denied.get("tool_name"),
                         "tool_use_id": denied.get("tool_use_id"),
                         "operation": fields.get("operation") or denied.get("tool_name"),
                         "reason": "The provider refused this operation because its tool permission was not available."}
                issues.append(issue)
                if self.logical_turn_id:
                    # The ONE producer banks it, with the provider and the tool call id
                    # that only this transport has: it is the sole link from a banked
                    # refusal to the provider's own call.
                    from laplace.native.tools import bank_failure
                    bank_failure(self.cwd, self.project, issue["operation"],
                                 fields.get("payload") or {}, issue["reason"],
                                 self.logical_turn_id,
                                 error_type="ProviderPermissionDenied", provider="claude",
                                 tool_use_id=issue["tool_use_id"])
            if issues:
                values["provider_issues"] = issues
                self.event({"type": "progress", "text": f"Claude refused {len(issues)} tool operation(s); inspect the saved failures."})
            # The terminal aggregate and per-model variant are separately retained.
            # Interrupted assistant snapshots are partial and never summed into a turn total.
            self.usage_facts.claude_terminal(result)
            values["usage_facts"]=self.usage_facts.snapshot()
            if self.delivery:values["delivery_receipt"]=self.delivery
            final_usage = result.get("usage")
            if not (isinstance(final_usage, dict)
                   and isinstance(final_usage.get("output_tokens"), int)
                   and not isinstance(final_usage.get("output_tokens"), bool)):
                # No independently reported complete turn aggregate; compatibility shows
                # only the latest observed request and labels the missing turn scope.
                final_usage = assistant_usage
                values["usage_basis"]={"counter_scope":"last_request","basis":"claude.assistant.usage","counter_domain":"main_conversation","completeness":"partial_turn"}
            else:values["usage_basis"]={"counter_scope":"logical_turn","basis":"claude.result.usage","counter_domain":"main_conversation"}
            projected = usage_projection("claude", final_usage, self.context_window_effective)
            if projected is not None:
                values["usage"] = projected
                context_selection=values["usage_facts"]["selected"]["context_snapshot"]
                values["context_tokens_used"] = context_selection["value"] if context_selection else None
            return turn_output(policy, values)
        finally:
            # The lifetime starts at successful spawn, including publication and
            # stdin delivery failures before stream parsing. Reap before return.
            if self.process is not None:
                if self.process.poll() is None:
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    self.process.wait(timeout=operator['limits']['cleanup_grace_seconds'] if operator else 3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass   # an existing interrupt may already have killed it
                    self.process.wait(timeout=3)
