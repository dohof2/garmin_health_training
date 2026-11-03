"""Per-turn accounting for the single reasoning agent and its domain tools."""
import json
import math
from contextvars import ContextVar

CURRENT = ContextVar('agent_runtime', default=None)


class BudgetExceeded(ValueError):
    pass


class Runtime:
    def __init__(self):
        self.kind = 'conversation'
        self.output_limit = 6000
        self.input_limit = 100000
        self.call_limit = 14
        self.output_ceiling = 24000
        self.usage = {k: 0 for k in ('model_calls', 'input_estimate', 'output_estimate',
                                    'input_tokens', 'output_tokens', 'reasoning_tokens', 'usage_reported')}

    def planning(self):
        self.input_limit = 200000
        self.call_limit = 22
        self.output_ceiling = 48000
        self.output_limit = 10000

    def reserve(self, prompt, instructions):
        size = math.ceil(len((instructions + json.dumps(prompt, ensure_ascii=False, default=str)).encode()) / 2)
        if (self.usage['model_calls'] >= self.call_limit or self.usage['input_estimate'] + size > self.input_limit
                or max(self.usage['output_estimate'], self.usage['output_tokens']) >= self.output_ceiling):
            raise BudgetExceeded('This turn reached its model allowance. The conversation and planning draft are retained; continue with a focused next step.')
        self.usage['model_calls'] += 1
        self.usage['input_estimate'] += size

    def observed(self, usage):
        if not usage:
            return
        def get(value, key):
            result = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
            return result
        for key in ('input_tokens', 'output_tokens'):
            value = get(usage, key)
            if type(value) is int:
                self.usage[key] += value
        details = get(usage, 'output_tokens_details') or {}
        reasoning = get(details, 'reasoning_tokens')
        if type(reasoning) is int:
            self.usage['reasoning_tokens'] += reasoning  # Already included in output_tokens.
        self.usage['usage_reported'] += 1

    def summary(self):
        return dict(self.usage)

    def output(self, text):
        self.usage['output_estimate'] += math.ceil(len(text.encode()) / 2)


class BudgetedProvider:
    def __init__(self, provider, runtime):
        self.provider, self.runtime = provider, runtime

    def generate(self, prompt, instructions, *, timeout_seconds=120):
        self.runtime.reserve(prompt, instructions)
        result = self.provider.generate(prompt, instructions, timeout_seconds=timeout_seconds)
        self.runtime.usage['output_estimate'] += math.ceil(len(result.encode()) / 2)
        return result


def output_options():
    runtime = CURRENT.get()
    return {'max_output_tokens': runtime.output_limit} if runtime else {}


def observe(usage):
    runtime = CURRENT.get()
    if runtime:
        runtime.observed(usage)
